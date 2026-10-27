import requests
import json
import logging
import time
from typing import Optional, List
from app.core.config import (
    AI_PROVIDER,
    OPENAI_API_KEY, OPENAI_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_EMBED_MODEL
)
from app.services.training_service import training_service
from app.core.ai_guardrails import OutputGuardrail, compose_ai_system_prompt

logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    """Raised when the configured AI provider cannot generate a response."""


# Fast response cache
_status_cache = {"last_check": 0, "status": None, "cache_duration": 30}
_conversation_memory = {}  # Store recent conversations per user

class AIService:
    """Unified AI service that can work with multiple providers"""
    
    def __init__(self):
        self.provider = AI_PROVIDER.lower()
    
    def generate(self, prompt: str, system: str = "You are KeepAI, a friendly study assistant who explains lessons in simple, clear, and easy-to-understand words.", 
                 user_id: str = "default", teaching_style: str = "simple", 
                 has_sources: bool = False, max_output_tokens: int = 1000) -> str:
        """Generate text using the configured AI provider."""
        training_info = training_service.generate_enhanced_response(
            prompt, teaching_style, "", has_sources
        )

        default_sys = "You are KeepAI, a friendly study assistant who explains lessons in simple, clear, and easy-to-understand words."
        if (not system or system == default_sys) and training_info.get('enhanced_instruction') and not has_sources:
            system = training_info['enhanced_instruction']
        system = compose_ai_system_prompt(system)

        try:
            if self.provider == "openai" and OPENAI_API_KEY:
                response = self._generate_openai(prompt, system, max_output_tokens)
            elif self.provider == "anthropic" and ANTHROPIC_API_KEY:
                response = self._generate_anthropic(prompt, system, max_output_tokens)
            elif self.provider == "gemini" and GEMINI_API_KEY:
                response = self._generate_gemini(prompt, system, max_output_tokens)
            else:
                raise AIProviderError(
                    f"The configured AI provider '{self.provider}' is not available."
                )
            if not response or not response.strip():
                raise AIProviderError("The AI service returned an empty response.")
        except AIProviderError:
            raise
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else None
            logger.error(
                "AI provider %s rejected generation request (model=%s, HTTP %s)",
                self.provider,
                self._configured_model(),
                status_code or "unknown",
            )
            raise AIProviderError(self._http_error_message(status_code)) from exc
        except requests.RequestException as exc:
            logger.error(
                "AI provider %s could not be reached (%s)",
                self.provider,
                type(exc).__name__,
            )
            raise AIProviderError(
                "The AI service could not be reached. Please retry in a moment."
            ) from exc
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            logger.error(
                "AI provider %s generation failed (%s, HTTP %s)",
                self.provider,
                type(exc).__name__,
                status_code or "n/a",
            )
            raise AIProviderError(
                "The AI service could not generate a response. Please try again."
            ) from exc

        safe_response = OutputGuardrail.validate_and_sanitize(response)
        _conversation_memory.setdefault(user_id, []).append({
            "prompt": prompt,
            "response": safe_response,
            "task_type": training_info['task_type'],
            "style": training_info['style']
        })
        _conversation_memory[user_id] = _conversation_memory[user_id][-5:]
        return safe_response

    def _configured_model(self) -> str:
        if self.provider == "gemini":
            return GEMINI_MODEL
        if self.provider == "openai":
            return OPENAI_MODEL
        if self.provider == "anthropic":
            return ANTHROPIC_MODEL
        return "configured model"

    @staticmethod
    def _http_error_message(status_code: Optional[int]) -> str:
        if status_code in (401, 403):
            return (
                "The AI provider rejected its credentials or access permissions. "
                "Please contact an administrator."
            )
        if status_code == 404:
            return (
                "The configured AI model is unavailable. Please contact an administrator "
                "to verify the model configuration."
            )
        if status_code == 429:
            return (
                "The AI provider is rate-limiting requests or its quota is exhausted. "
                "Please wait and try again, or contact an administrator."
            )
        if status_code is not None and status_code >= 500:
            return "The AI provider is temporarily unavailable. Please retry in a moment."
        if status_code == 400:
            return (
                "The AI provider rejected the generation request. Please contact an "
                "administrator to verify the model settings."
            )
        return "The AI service could not complete the request. Please try again."

    @staticmethod
    def _post_with_retries(url: str, *, json: dict, timeout: int):
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(2):
            try:
                response = requests.post(url, json=json, timeout=timeout)
            except requests.RequestException:
                if attempt == 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
                continue

            if response.status_code in retryable_statuses and attempt < 1:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(max(float(retry_after), 0), 3) if retry_after else 0.5 * (attempt + 1)
                except (TypeError, ValueError):
                    delay = 0.5 * (attempt + 1)
                if delay:
                    time.sleep(delay)
                continue

            response.raise_for_status()
            return response

        raise requests.RequestException("The AI provider did not return a response.")

    def generate_stream(self, prompt: str, system: str = "You are KeepAI, a friendly study assistant who explains lessons in simple, clear, and easy-to-understand words.",
                        user_id: str = "default", teaching_style: str = "simple",
                        has_sources: bool = False, timeout: int = 240):
        """Stream provider-generated tokens without substituting a canned answer."""
        full_tokens = []
        try:
            training_info = training_service.generate_enhanced_response(
                prompt, teaching_style, "", has_sources
            )
            default_sys = "You are KeepAI, a friendly study assistant who explains lessons in simple, clear, and easy-to-understand words."
            if (not system or system == default_sys) and training_info.get('enhanced_instruction') and not has_sources:
                system = training_info['enhanced_instruction']
            system = compose_ai_system_prompt(system)

            if self.provider == "gemini" and GEMINI_API_KEY:
                for token in self._generate_gemini_stream(prompt, system, timeout=timeout):
                    full_tokens.append(token)
            elif self.provider == "openai" and OPENAI_API_KEY:
                response = self._generate_openai(prompt, system)
                full_tokens.append(response)
            elif self.provider == "anthropic" and ANTHROPIC_API_KEY:
                response = self._generate_anthropic(prompt, system)
                full_tokens.append(response)
            else:
                raise AIProviderError(
                    f"The configured AI provider '{self.provider}' is not available."
                )
            if not full_tokens:
                raise AIProviderError("The AI service returned an empty response.")
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            logger.error(
                "AI provider %s streaming failed (%s, HTTP %s)",
                self.provider,
                type(e).__name__,
                status_code or "n/a",
            )
            raise AIProviderError(
                "The AI service could not generate a response. Please try again."
            ) from e

        if full_tokens:
            final_resp = OutputGuardrail.validate_and_sanitize("".join(full_tokens))
            if not final_resp.strip():
                raise AIProviderError("The AI service returned an empty response.")
            for start in range(0, len(final_resp), 80):
                yield final_resp[start:start + 80]
            if user_id not in _conversation_memory:
                _conversation_memory[user_id] = []
            _conversation_memory[user_id].append({
                "prompt": prompt,
                "response": final_resp,
                "task_type": "tutor_explanation",
                "style": teaching_style
            })
            _conversation_memory[user_id] = _conversation_memory[user_id][-5:]


    def _generate_training_enhanced_response(self, prompt: str, system: str, user_id: str, training_info: dict) -> str:
        """Generate responses enhanced with professional training data"""
        task_type = training_info['task_type']
        style = training_info['style']
        example_pattern = training_info.get('example_pattern')
        
        # Use training examples as templates for better responses
        if example_pattern:
            return self._apply_training_pattern(prompt, example_pattern, style, user_id)
        
        # Fallback to task-specific professional responses
        return self._generate_professional_response(prompt, task_type, style, user_id)
    
    def _apply_training_pattern(self, prompt: str, example: dict, style: str, user_id: str) -> str:
        """Apply training pattern to generate professional responses"""
        task_type = example.get('metadata', {}).get('task')
        
        if task_type == 'tutor_explanation':
            return self._generate_tutor_explanation(prompt, style, example)
        elif task_type == 'quiz_generation':
            return self._generate_quiz_response(prompt, example)
        elif task_type == 'summarization':
            return self._generate_summary_response(prompt, style)
        elif task_type == 'flashcard_generation':
            return self._generate_flashcard_response(prompt, style)
        elif task_type == 'adaptive_review':
            return self._generate_review_response(prompt, style, user_id)
        else:
            return self._generate_professional_response(prompt, task_type, style, user_id)
    
    def _generate_tutor_explanation(self, prompt: str, style: str, example: dict) -> str:
        """Generate tutor explanations based on training patterns"""
        topic = self._extract_topic(prompt)
        
        if style == 'taglish':
            return f"""**{topic.title()}** (Paliwanag):

{self._get_concept_explanation(prompt)}

Sa madaling salita, ito ay isang simpleng paraan para matutunan at magamit ang konseptong ito sa iyong aralin.

**Mahahalagang dapat tandaan:**
- Ang pangunahing ibig sabihin nito
- Paano ito ginagamit sa totoong buhay  
- Paano ito konektado sa iba mo pang mga aralin

**Tip:** Tandaan na silipin din ang lesson notes mo para mas madali mong matandaan! 📚

May gusto ka pa bang itanong? Magtanong ka lang o mag-upload ng notes mo para sa mas detalyadong tulong! ✨"""
        
        elif style == 'professor':
            return f"""**What it means:** {self._get_concept_explanation(prompt)}

**How it works:**
This concept gives us a clear and organized way to understand and solve problems in this subject.

**Key points to remember:**
- The main definition and ideas
- Practical examples of where it is used
- How it connects to other topics you are studying

**Study Tip:** Check your lecture slides to see how your teacher defined it for class.

**Questions?** Let me know which part you want to explore more!"""
        
        else:  # simple / general style
            return f"""**Understanding {topic.title()}:**

**What is it?**
{self._get_concept_explanation(prompt)}

**Key Points:**
• **Main Idea**: The basic meaning and principles behind this topic
• **Real-World Use**: Where and how people actually use this in real life
• **Why It Matters**: How this helps you understand your lessons better

**How to Study This:**
1. Learn the basic definition first
2. Look at everyday examples
3. Practice explaining it in your own words

**Next Step:** Upload your lesson notes if you want explanations based directly on your class materials! 📚✨"""
    
    def _generate_quiz_response(self, prompt: str, example: dict) -> str:
        """Generate quiz-style responses"""
        if "quiz" in prompt.lower() or "test" in prompt.lower():
            topic = self._extract_topic(prompt)
            return f"""**Practice Quiz on {topic.title()}** 📝

**Question 1:** Which best describes {topic}?
A) A simple process with limited applications
B) A clear, structured way to solve problems in this subject
C) An outdated method no longer used
D) A theory with no practical use

**Correct Answer:** B) A clear, structured way to solve problems in this subject

**Explanation:** {self._get_concept_explanation(prompt)}

**Study Tip:** For quizzes tailored directly to your class, upload your course notes so I can generate questions directly from your lessons!

**Want more practice questions?** Just ask and I will create more for you! 🎯"""
        
        return self._generate_professional_response(prompt, "quiz_generation", "simple", "default")
    
    def _generate_summary_response(self, prompt: str, style: str) -> str:
        """Generate summary-style responses"""
        topic = self._extract_topic(prompt)
        
        return f"""**Summary: {topic.title()}** 📋

**Main Points:**
1. **What it is**: {self._get_concept_explanation(prompt)}
2. **Important Parts**: The essential pieces that make up this topic
3. **Where it is used**: Real-world examples and everyday applications
4. **Why it matters**: Why this topic is important for your class

**Key Takeaways:**
• Start with the basics before moving to harder topics
• Connect this lesson with what you learned previously

**Want a summary of your specific notes?** Upload your PDF and I will summarize your exact lesson! 📚✨"""
    
    def _generate_flashcard_response(self, prompt: str, style: str) -> str:
        """Generate flashcard-style responses"""
        topic = self._extract_topic(prompt)
        
        return f"""**Flashcard Set: {topic.title()}** 🗂️

**Card 1:**
**Front:** What is {topic}?
**Back:** {self._get_concept_explanation(prompt)}

**Card 2:** 
**Front:** Why is {topic} important?
**Back:** It helps us solve problems and understand how things work in this subject.

**Card 3:**
**Front:** How is {topic} used?
**Back:** Through simple steps that can be applied to real-world situations.

**Study Tip:** Review these cards regularly to test yourself!

**Want more cards?** Upload your lesson file and I can generate cards directly from your notes! 📚⚡"""
    
    def _generate_review_response(self, prompt: str, style: str, user_id: str) -> str:
        """Generate adaptive review responses"""
        previous_convos = _conversation_memory.get(user_id, [])
        topic = self._extract_topic(prompt)
        
        review_areas = []
        if previous_convos:
            prev_topics = [self._extract_topic(conv.get('prompt', '')) for conv in previous_convos[-3:]]
            review_areas.extend(prev_topics)
        
        return f"""**Study Review Session** 📖

**Current Topic: {topic.title()}**
**Status:** {'Continuing our study session' if previous_convos else 'New topic'}

**Easy Study Plan:**
1. **Basics First**: Make sure you understand the simple definition
2. **Practice Examples**: Look at practical real-life examples
3. **Connect Ideas**: Relate this to what you studied before
4. **Self-Test**: Try answering a few practice questions

{f"**Previous Topics to Review:** {', '.join(set(review_areas))}" if review_areas else ""}

**Helpful Tip:** Upload your lesson files so we can review the exact topics from your class! 🎯"""
    
    def _generate_professional_response(self, prompt: str, task_type: str, style: str, user_id: str) -> str:
        """Generate helpful responses in simple words"""
        topic = self._extract_topic(prompt)
        
        base_response = f"""**Study Assistant Response** 🎓

**Topic:** {topic.title()}

**Explanation:**
{self._get_concept_explanation(prompt)}

**Simple Breakdown:**
- **Core Meaning**: What this topic is really about
- **Everyday Use**: How it applies to real-life situations
- **In Class**: How this connects to your other lessons

**I am here to help!** If you want explanations tailored directly to your syllabus, just upload your course notes. Feel free to ask any question in plain words! 📚✨"""
        
        return base_response
    
    def _explain_main_concepts(self, topic: str, is_follow_up: bool) -> str:
        """Explain main concepts of a topic"""
        if "machine learning" in topic.lower():
            return """**Main Concepts in Machine Learning:**

**1. Core Definition** 🧠
Machine learning is a method of data analysis that automates analytical model building using algorithms that iteratively learn from data.

**2. Key Components** 📊
• **Data**: The foundation - training examples that teach the algorithm
• **Algorithms**: Mathematical procedures that find patterns
• **Models**: The result - a system that can make predictions
• **Training**: The process of teaching the algorithm using data

**3. Learning Types** 🎯
• **Supervised Learning**: Learning with labeled examples (like having answer keys)
• **Unsupervised Learning**: Finding hidden patterns in data without labels
• **Reinforcement Learning**: Learning through trial and error with rewards

**4. Real-World Applications** 🌟
• Recommendation systems (Netflix, Spotify)
• Image recognition (medical diagnosis, autonomous cars)
• Natural language processing (chatbots, translation)

Would you like me to dive deeper into any of these concepts?"""
        
        return f"""**Main Points in {topic.title()}:**

**1. Basic Idea** 📚
The simple meaning and main purpose of this topic.

**2. Key Parts** 🔧
The important pieces that work together to make it function.

**3. Real-World Examples** 🎯
Where you can see this in action in daily life or technology.

**4. Why It Matters** 💡
Why learning this makes the rest of your lessons easier.

For more specific help with {topic}, upload your course notes so I can explain it directly from your lessons!"""
    
    def _explain_simply(self, topic: str, prompt_lower: str) -> str:
        """Provide simple explanations"""
        if "machine learning" in topic.lower():
            if "taglish" in prompt_lower:
                return """**Machine Learning in Simple Taglish:**

**Ano ang Machine Learning?** 🤖
Ito yung paraan kung saan tinuturuan natin ang computer na matuto mag-isa gamit ang mga halimbawa, para hindi na natin kailangan i-program ang bawat detalye.

**Paano ito gumagana?** 
1. **Data muna** - Nagbibigay tayo ng maraming examples sa computer
2. **Practice** - Sinasanay natin ito gamit ang examples  
3. **Sagot** - Kapag natuto na ito, kaya na nitong magbigay ng tamang hula o desisyon sa mga bagong bagay

**Simpleng Halimbawa:**
Para bang tinuturuan mo ang isang bata na makilala ang aso. Ipapakita mo sa kanya ang maraming larawan ng aso, hanggang sa kaya na niyang tukuyin kung aso nga ang nakikita niya kahit bagong larawan pa ito.

**Saan ito ginagamit?**
• Pag-recognize ng mukha sa mga larawan
• Pag-suggest ng mga kanta o palabas na magugustuhan mo
• Automatic translation ng iba't ibang wika

Madali lang, di ba? Magtanong ka lang kung may gusto ka pang linawin! 😊"""
            
            return """**Machine Learning - Simple Explanation** 🤖

Think of it like teaching a child to recognize things:

**What it is:**
Machine learning is giving a computer lots of examples so it can learn to make decisions on its own, without someone coding every single rule.

**How it works:**
1. **Show examples** - Like showing a child pictures of cats
2. **Let it practice** - The computer spots patterns in those pictures  
3. **Test it** - Show it a brand-new picture it has never seen before
4. **It recognizes** - "That's a cat!" (because it learned the pattern)

**Everyday examples:**
• Recommendations for movies and music you might like
• Your phone recognizing your face or voice
• Email filtering out junk and spam messages

It is basically finding patterns - just really smart and fast! 🧠✨"""
        
        return f"Let me explain {topic} in simple words:\n\n{topic.title()} is all about learning the basic rules and patterns so you can solve problems step by step. Think of it like learning the rules of a game before playing.\n\nFor an explanation directly from your class materials, upload your lesson file and I will break down the exact notes for you!"
    
    def _step_by_step_explanation(self, topic: str) -> str:
        """Provide step-by-step explanations"""
        return f"""**Step-by-Step Guide to Understanding {topic.title()}** 📋

**Step 1: Foundation Building** 🏗️
• Start with basic definitions and core concepts
• Understand the terminology and key vocabulary
• Identify the main components involved

**Step 2: Conceptual Understanding** 🧠  
• Learn how different parts connect and interact
• Understand the underlying principles and theory
• See the big picture of how everything fits together

**Step 3: Practical Application** 🎯
• Study real-world examples and case studies
• Practice with guided exercises and problems
• Apply concepts to familiar scenarios

**Step 4: Skill Development** 💪
• Work through progressively challenging problems
• Practice until the process becomes natural
• Develop problem-solving strategies

**Step 5: Mastery & Integration** ⭐
• Connect this topic to other related concepts
• Evaluate and critique different approaches
• Create your own examples and applications

**Next Steps:** Upload your specific course materials so I can provide detailed, curriculum-aligned explanations for each step!"""
    
    def _provide_example(self, topic: str) -> str:
        """Provide practical examples"""
        if "machine learning" in topic.lower():
            return """**Practical Machine Learning Example** 🎯

**Scenario: Email Spam Detection** 📧

**The Problem:**
Your email provider needs to automatically identify spam emails without reading every single email manually.

**How Machine Learning Solves It:**

1. **Training Data Collection** 📊
   • Gather 100,000 emails already labeled as "spam" or "not spam"
   • Include examples like: promotional emails, phishing attempts, normal messages

2. **Feature Identification** 🔍
   • Words that appear frequently in spam ("FREE!", "URGENT!", "CLICK NOW!")
   • Sender patterns (unknown addresses, suspicious domains)
   • Email structure (excessive links, all caps, etc.)

3. **Algorithm Training** 🤖
   • Feed all examples to the algorithm
   • It learns patterns: "Emails with 'FREE!' + unknown sender = likely spam"
   • Creates a model that can predict spam probability

4. **Real-World Application** ✅
   • New email arrives: "FREE MONEY! CLICK NOW!"
   • Model analyzes: unknown sender + "FREE!" + "CLICK NOW" = 95% spam probability
   • Action: Move to spam folder

**Result:** Your inbox stays clean automatically! 🎉

This same process works for Netflix recommendations, medical diagnosis, and autonomous cars!"""
        
        return f"""**Practical Example of {topic.title()}** 💡

Here's how {topic} works in a real-world context:

**Scenario Setup:**
Consider a common problem where this concept would be applied in professional or academic settings.

**Implementation:**
• **Step 1**: Identify the core challenge or opportunity
• **Step 2**: Apply the key principles we've discussed  
• **Step 3**: Execute using established methodologies
• **Step 4**: Evaluate results and refine approach

**Outcome:**
This demonstrates how theoretical knowledge translates into practical solutions.

**Want a more specific example?** Upload your course materials and I can provide detailed examples directly from your curriculum!"""
    
    def _define_concept(self, topic: str) -> str:
        """Provide clear definitions"""
        if "machine learning" in topic.lower():
            return """**Definition: Machine Learning** 🤖

**Simple Definition:**
Machine learning is a type of artificial intelligence where computers learn to make predictions or decisions by finding patterns in data, without being explicitly programmed for each specific task.

**Technical Definition:**
Machine learning is a computational method that enables systems to automatically improve their performance on a specific task through experience, using statistical techniques to progressively improve predictions or decisions based on data.

**Key Characteristics:**
• **Learns from data** - Uses examples to understand patterns
• **Makes predictions** - Can work with new, unseen information  
• **Improves over time** - Gets better with more data and experience
• **Automates decisions** - Reduces need for manual programming

**What it's NOT:**
• It's not traditional programming (if-then rules)
• It's not magic - it needs good data and proper setup
• It's not always 100% accurate - it makes educated guesses

**In One Sentence:**
Machine learning teaches computers to recognize patterns in data so they can make smart predictions about new information they haven't seen before.

**Think of it like:** Teaching a computer to be really good at educated guessing! 🎯"""
        
        return f"""**Definition: {topic.title()}** 📖

**In Simple Words:**
{self._get_concept_explanation(prompt)}

**Key Things to Know:**
• The basic meaning behind what it does
• How it is used in real situations
• Why it is important in your lessons

**For Precise Definitions:** Upload your lesson notes and I will give you the exact definitions straight from your course files!"""
    
    def _intelligent_general_response(self, prompt: str, is_follow_up: bool) -> str:
        """Generate intelligent general responses for any question"""
        topic = self._extract_topic(prompt)
        
        responses = [
            f"""I understand you're asking about **{topic}**. Let me help you with that! 📚

Here is a simple explanation:
{self._get_concept_explanation(prompt)}

**How to study this:**
• Learn the main definition first
• Look at everyday examples  
• Upload your lesson notes if you want explanations based on your class material!

**I am here to help!** Feel free to ask follow-up questions anytime. 🎯✨""",

            f"""Great question about **{topic}**! 🤔

I can explain this simply. For answers based directly on your class lessons, uploading your course files is best.

**What I can do right now:**
• Give you simple definitions and explanations
• Break down tricky ideas into easy steps
• Give real-world examples
• Help you prepare for quizzes and tests

**Want specific help?** Upload your lecture slides or notes, and I will tailor my answers directly to what you are studying! 💡""",

            f"""I'd be happy to help you understand **{topic}** better! 🌟

**Here is how I can assist:**

📖 **Simple Explanations** - Break down ideas into plain English
🔍 **Real Examples** - Give everyday applications you can relate to
📋 **Study Help** - Create summaries, key points, and flashcards
💭 **Questions & Answers** - Answer any question you have about your lessons

**Tip:** Upload your study files and I will answer directly using your class notes.

**What part would you like to explore first?** Just ask! 🎯"""
        ]
        
        # Use prompt content to select varied response
        import hashlib
        hash_val = int(hashlib.md5(prompt.encode()).hexdigest(), 16) % len(responses)
        return OutputGuardrail.validate_and_sanitize(responses[hash_val])
    
    def _extract_topic(self, prompt: str) -> str:
        """Extract the main topic from user prompt"""
        # Remove common question words
        words = prompt.lower().replace("what is", "").replace("explain", "").replace("step by step", "").strip()
        # Take first few significant words
        topic_words = [w for w in words.split()[:3] if len(w) > 2]
        return " ".join(topic_words) or "this topic"
    
    def _get_concept_explanation(self, prompt: str) -> str:
        """Generate concept explanation based on prompt keywords in simple words"""
        if "machine learning" in prompt.lower():
            return "Machine learning teaches computers to learn from examples and improve over time, without having to code every single rule."
        elif "data" in prompt.lower():
            return "Data processing means collecting, organizing, and understanding information to make smart decisions."
        elif "algorithm" in prompt.lower():
            return "An algorithm is a step-by-step set of clear instructions to solve a problem or complete a task."
        else:
            topic = self._extract_topic(prompt)
            return f"{topic.title()} is a clear way to understand and solve problems step-by-step in this subject."
    
    def _generate_contextual_response(self, prompt: str, is_follow_up: bool = False) -> str:
        """Generate varied contextual responses with conversation awareness"""
        topic = self._extract_topic(prompt)
        
        if is_follow_up:
            response_templates = [
                f"Continuing with our discussion on **{topic}**:\n\n**Key Points:**\n- This idea is widely used in modern technology\n- It focuses on solving real-world problems simply\n- It connects well with what you have already learned\n\nFor details from your class, upload your lesson file!",
                
                f"Looking deeper at **{topic}**:\n\n**Things to Remember:**\n- It provides simple steps to handle practical situations\n- Practice and examples will help you master it faster\n- It is a foundational part of this subject\n\nUpload your documents to see how your teacher defined it!"
            ]
        else:
            response_templates = [
                f"Regarding **'{topic}'**, here is a simple overview:\n\n{self._get_concept_explanation(prompt)}\n\nFor answers matching your exact class syllabus, please upload your lesson notes.",
                
                f"I understand you are asking about **{topic}**:\n\n• The core idea is simple and practical\n• It helps you solve everyday problems in this field\n• Upload your course file for answers tailored directly to your class!",
                
                f"Great question about **{topic}**!\n\n• It provides clear steps to understand this topic\n• Learning the basics first makes the rest much easier\n• Upload your notes for lesson-specific explanations!"
            ]
        
        # Vary responses based on prompt content
        import hashlib
        hash_val = int(hashlib.md5(prompt.encode()).hexdigest(), 16) % len(response_templates)
        return OutputGuardrail.validate_and_sanitize(response_templates[hash_val])
    
    def _generate_openai(self, prompt: str, system: str, max_output_tokens: int = 1000) -> str:
        """Generate using OpenAI API"""
        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_output_tokens,
                "temperature": 0.7
            },
            timeout=60
        )
        response.raise_for_status()
        choice = response.json()["choices"][0]
        if choice.get("finish_reason") == "length":
            raise AIProviderError(
                "The tutor response reached its length limit. Please ask a more focused question."
            )
        return choice["message"]["content"]
    
    def _generate_anthropic(self, prompt: str, system: str, max_output_tokens: int = 1000) -> str:
        """Generate using Anthropic Claude API"""
        if not ANTHROPIC_API_KEY:
            raise ValueError("Anthropic API key not configured")
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": max_output_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        if data.get("stop_reason") == "max_tokens":
            raise AIProviderError(
                "The tutor response reached its length limit. Please ask a more focused question."
            )
        return data["content"][0]["text"]
    
    def _generate_gemini(self, prompt: str, system: str, max_output_tokens: int = 1000) -> str:
        """Generate using Google Gemini API"""
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key not configured")
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "temperature": 0.7
            }
        }
        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        response = self._post_with_retries(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
            timeout=60,
        )
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no response candidates")
        if candidates[0].get("finishReason") == "MAX_TOKENS":
            raise AIProviderError(
                "The tutor response reached its length limit. Please ask a more focused question."
            )
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        if not text.strip():
            raise ValueError("Gemini returned an empty response")
        return text

    def _generate_gemini_stream(self, prompt: str, system: str, timeout: int = 60):
        """Stream tokens directly from Google Gemini API"""
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key not configured")

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "maxOutputTokens": 1800,
                "temperature": 0.7
            }
        }
        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
        response = requests.post(
            url,
            json=payload,
            stream=True,
            timeout=timeout
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    try:
                        chunk = json.loads(decoded[6:])
                        candidates = chunk.get("candidates", [])
                        if candidates:
                            if candidates[0].get("finishReason") == "MAX_TOKENS":
                                raise AIProviderError(
                                    "The tutor response reached its length limit. Please ask a more focused question."
                                )
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for part in parts:
                                text = part.get("text", "")
                                if text:
                                    yield text
                    except json.JSONDecodeError:
                        continue

    def _embed_gemini(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings using Google Gemini API"""
        if not GEMINI_API_KEY or not texts:
            return [[0.1] * 768 for _ in texts]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_EMBED_MODEL}:batchEmbedContents?key={GEMINI_API_KEY}"
        embeddings = []
        batch_size = 50
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            payload = {
                "requests": [
                    {
                        "model": f"models/{GEMINI_EMBED_MODEL}",
                        "content": {"parts": [{"text": t}]}
                    }
                    for t in batch
                ]
            }
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("embeddings", []):
                embeddings.append(item.get("values", []))
        return embeddings

    def _generate_fallback(self, prompt: str, system: str) -> str:
        """Fallback response when no AI provider is available"""
        return """I'm KeepAI, your learning assistant! However, I need an AI service to be configured to provide intelligent responses. 
        
Please configure your Google Gemini API key in the .env file:
  GEMINI_API_KEY=your_api_key_here

Once configured, I can help you with:
- Answering questions about your uploaded materials
- Creating study summaries
- Generating practice quizzes
- Explaining complex topics in simple terms

For now, I can still help you organize your library and track your study progress!"""

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts using Gemini provider"""
        if self.provider == "gemini" and GEMINI_API_KEY:
            try:
                return self._embed_gemini(texts)
            except Exception as e:
                print(f"⚠️ Gemini embedding notice: {e}. Falling back.")
                return [[0.1] * 768 for _ in texts]
        else:
            # Fallback mock embeddings
            return [[0.1] * 768 for _ in texts]

    def get_status(self) -> dict:
        """Get status with caching for fast response"""
        current_time = time.time()
        
        # Use cached status if recent
        if (current_time - _status_cache["last_check"] < _status_cache["cache_duration"] 
            and _status_cache["status"]):
            return _status_cache["status"]
        
        status = {"provider": self.provider, "status": "checking"}
        
        try:
            if self.provider == "gemini":
                if GEMINI_API_KEY:
                    status.update({
                        "status": "configured",
                        "configured_chat_model": GEMINI_MODEL,
                        "configured_embed_model": GEMINI_EMBED_MODEL,
                        "installed_models": [GEMINI_MODEL, GEMINI_EMBED_MODEL],
                        "message": "Gemini API key is configured; generation is verified per request."
                    })
                else:
                    status.update({
                        "status": "not_configured",
                        "message": "Gemini API key not configured"
                    })
            elif self.provider == "openai":
                status.update({
                    "status": "configured" if OPENAI_API_KEY else "not_configured",
                    "model": OPENAI_MODEL,
                    "message": "API key not set" if not OPENAI_API_KEY else "Ready"
                })
            else:
                status.update({"status": "ready", "message": "AI Tutor ready (local academic engine)"})
                
        except Exception as e:
            status.update({"status": "ready", "message": f"AI Tutor active - {str(e)}"})
        
        # Cache the result
        _status_cache["last_check"] = current_time
        _status_cache["status"] = status
        return status

# Global AI service instance
ai_service = AIService()

# Legacy functions for backward compatibility
def generate(prompt: str, system: str = "You are KeepAI, a friendly study assistant who explains lessons in simple, clear, and easy-to-understand words.", 
             user_id: str = "default", teaching_style: str = "simple", 
             has_sources: bool = False, system_instruction: Optional[str] = None,
             max_output_tokens: int = 1000) -> str:
    if system_instruction is not None:
        system = system_instruction
    return ai_service.generate(
        prompt,
        system,
        user_id,
        teaching_style,
        has_sources,
        max_output_tokens,
    )

def generate_stream(prompt: str, system: str = "You are KeepAI, a friendly study assistant who explains lessons in simple, clear, and easy-to-understand words.", 
                    user_id: str = "default", teaching_style: str = "simple", 
                    has_sources: bool = False, timeout: int = 240):
    return ai_service.generate_stream(prompt, system, user_id, teaching_style, has_sources, timeout)

def embed_many(texts: List[str]) -> List[List[float]]:
    return ai_service.embed_many(texts)
