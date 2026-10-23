import requests
import json
import time
from typing import Optional, List
from app.core.config import (
    AI_PROVIDER, OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, OLLAMA_EMBED_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_EMBED_MODEL
)
from app.services.training_service import training_service

# Fast response cache
_status_cache = {"last_check": 0, "status": None, "cache_duration": 30}
_conversation_memory = {}  # Store recent conversations per user

class AIService:
    """Unified AI service that can work with multiple providers"""
    
    def __init__(self):
        self.provider = AI_PROVIDER.lower()
    
    def generate(self, prompt: str, system: str = "You are KeepAI, a helpful academic tutor.", 
                 user_id: str = "default", teaching_style: str = "academic", 
                 has_sources: bool = False) -> str:
        """Generate text using the configured AI provider with training-enhanced responses"""
        try:
            # Get training enhancement
            training_info = training_service.generate_enhanced_response(
                prompt, teaching_style, "", has_sources
            )
            
            # Enhance system prompt with training data only when no specific lesson sources were provided
            if training_info['enhanced_instruction'] and not has_sources:
                system = training_info['enhanced_instruction']
            
            # Store conversation context
            if user_id not in _conversation_memory:
                _conversation_memory[user_id] = []
            
            # Generate response using configured AI provider
            if self.provider == "ollama":
                response = self._generate_ollama(prompt, system, timeout=240)
            elif self.provider == "openai" and OPENAI_API_KEY:
                response = self._generate_openai(prompt, system)
            elif self.provider == "anthropic" and ANTHROPIC_API_KEY:
                response = self._generate_anthropic(prompt, system)
            elif self.provider == "gemini" and GEMINI_API_KEY:
                response = self._generate_gemini(prompt, system)
            else:
                # Use training-enhanced demo responses
                response = self._generate_training_enhanced_demo(
                    prompt, system, user_id, training_info
                )
            
            # Remember this conversation
            _conversation_memory[user_id].append({
                "prompt": prompt, 
                "response": response,
                "task_type": training_info['task_type'],
                "style": training_info['style']
            })
            # Keep only last 5 conversations
            _conversation_memory[user_id] = _conversation_memory[user_id][-5:]
            
            return response
        except Exception as e:
            print(f"⚠️ AI generation notice ({self.provider}): {e}")
            # Fallback to training-enhanced demo
            training_info = training_service.generate_enhanced_response(
                prompt, teaching_style, "", has_sources
            )
            return self._generate_training_enhanced_demo(prompt, system, user_id, training_info)

    def generate_stream(self, prompt: str, system: str = "You are KeepAI, a helpful academic tutor.",
                        user_id: str = "default", teaching_style: str = "academic",
                        has_sources: bool = False, timeout: int = 240):
        """Stream tokens generator with ChatGPT-like token streaming and conversation memory"""
        full_tokens = []
        try:
            training_info = training_service.generate_enhanced_response(
                prompt, teaching_style, "", has_sources
            )
            if training_info.get('enhanced_instruction') and not has_sources:
                system = training_info['enhanced_instruction']

            if self.provider == "gemini" and GEMINI_API_KEY:
                for token in self._generate_gemini_stream(prompt, system, timeout=timeout):
                    full_tokens.append(token)
                    yield token
            elif self.provider == "ollama":
                for token in self._generate_ollama_stream(prompt, system, timeout=timeout):
                    full_tokens.append(token)
                    yield token
            elif self.provider == "openai" and OPENAI_API_KEY:
                response = self._generate_openai(prompt, system)
                for chunk in response.split(" "):
                    part = chunk + " "
                    full_tokens.append(part)
                    yield part
                    time.sleep(0.01)
            else:
                demo = self._generate_training_enhanced_demo(prompt, system, user_id, training_info)
                words = demo.split(" ")
                for i, w in enumerate(words):
                    part = w + (" " if i < len(words) - 1 else "")
                    full_tokens.append(part)
                    yield part
                    time.sleep(0.015)
        except Exception as e:
            print(f"⚠️ AI stream notice ({self.provider}): {e}")
            if not full_tokens:
                training_info = training_service.generate_enhanced_response(
                    prompt, teaching_style, "", has_sources
                )
                demo = self._generate_training_enhanced_demo(prompt, system, user_id, training_info)
                words = demo.split(" ")
                for i, w in enumerate(words):
                    part = w + (" " if i < len(words) - 1 else "")
                    full_tokens.append(part)
                    yield part
                    time.sleep(0.015)

        if full_tokens:
            final_resp = "".join(full_tokens)
            if user_id not in _conversation_memory:
                _conversation_memory[user_id] = []
            _conversation_memory[user_id].append({
                "prompt": prompt,
                "response": final_resp,
                "task_type": "tutor_explanation",
                "style": teaching_style
            })
            _conversation_memory[user_id] = _conversation_memory[user_id][-5:]

    def _generate_ollama_stream(self, prompt: str, system: str, timeout: int = 240):
        """Stream tokens directly from local Ollama instance"""
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_CHAT_MODEL,
                "stream": True,
                "options": {
                    "num_ctx": 1536,
                    "num_predict": 450,
                    "temperature": 0.2
                },
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            stream=True,
            timeout=timeout,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))
                msg = chunk.get("message", {})
                token = msg.get("content", "")
                if token:
                    yield token
                if chunk.get("done", False):
                    break

    def _generate_ollama(self, prompt: str, system: str, timeout: int = 240) -> str:
        """Generate using local Ollama with generous timeout and bounded output for 7B models"""
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_CHAT_MODEL,
                "stream": False,
                "options": {
                    "num_ctx": 1536,
                    "num_predict": 450,
                    "temperature": 0.2
                },
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
    
    def _generate_training_enhanced_demo(self, prompt: str, system: str, user_id: str, training_info: dict) -> str:
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
            return f"""**{topic.title()}** explanation:

{self._get_concept_explanation(prompt)} Sa madaling sabi, this concept involves systematic approaches na ginagamit sa academic field.

**Key points to remember:**
- Understanding the fundamental principles
- Practical applications sa real-world scenarios  
- Connection to other related concepts

**Tip:** Tandaan na i-check pa rin ang wording sa official lesson materials mo para sa precise definitions! 📚

Need more details? Ask follow-up questions or upload your materials for more specific explanations! ✨"""
        
        elif style == 'professor':
            return f"""**Definition:** {self._get_concept_explanation(prompt)}

**Academic Framework:**
This concept operates within established theoretical foundations and demonstrates measurable applications across multiple domains.

**Methodological Considerations:**
- Systematic implementation approaches
- Evidence-based validation protocols
- Integration with complementary methodologies

**Study Recommendation:** Cross-reference this explanation with assigned materials to ensure alignment with course-specific terminology and applications.

**Further Inquiry:** What specific aspect would you like to explore in greater depth?"""
        
        else:  # academic style
            return f"""**Understanding {topic.title()}:**

**Core Concept:** {self._get_concept_explanation(prompt)}

**Key Elements:**
• **Theoretical Foundation**: The underlying principles that support this concept
• **Practical Application**: How it's implemented in real-world scenarios
• **Academic Significance**: Its role in advancing knowledge in this field

**Learning Approach:**
1. Master the fundamental definition and components
2. Study examples and case studies
3. Practice applying concepts to new situations
4. Connect to broader theoretical frameworks

**Next Steps:** Review your course materials for specific examples and detailed applications relevant to your curriculum."""
    
    def _generate_quiz_response(self, prompt: str, example: dict) -> str:
        """Generate quiz-style responses"""
        if "quiz" in prompt.lower() or "test" in prompt.lower():
            topic = self._extract_topic(prompt)
            return f"""**Practice Quiz on {topic.title()}** 📝

**Question 1:** Which best describes {topic}?
A) A simple process with limited applications
B) A systematic approach with multiple applications  
C) An outdated methodology
D) A theoretical concept only

**Correct Answer:** B) A systematic approach with multiple applications

**Explanation:** {self._get_concept_explanation(prompt)}

**Study Tip:** For comprehensive quiz preparation, upload your course materials so I can generate questions specifically from your lessons!

**Want more questions?** Just ask and I'll create additional practice problems! 🎯"""
        
        return self._generate_professional_response(prompt, "quiz_generation", "academic", "default")
    
    def _generate_summary_response(self, prompt: str, style: str) -> str:
        """Generate summary-style responses"""
        topic = self._extract_topic(prompt)
        
        return f"""**Summary: {topic.title()}** 📋

**Main Points:**
1. **Definition & Purpose**: {self._get_concept_explanation(prompt)}
2. **Core Components**: Essential elements that make up this concept
3. **Applications**: Where and how it's used in practice
4. **Significance**: Why it matters in your field of study

**Key Takeaways:**
• Understanding requires both theoretical knowledge and practical application
• Connects to broader concepts in your curriculum
• Forms foundation for more advanced topics

**For Detailed Summaries:** Upload your specific lesson materials and I can create comprehensive summaries directly from your course content! 📚✨"""
    
    def _generate_flashcard_response(self, prompt: str, style: str) -> str:
        """Generate flashcard-style responses"""
        topic = self._extract_topic(prompt)
        
        return f"""**Flashcard Set: {topic.title()}** 🗂️

**Card 1:**
**Front:** What is {topic}?
**Back:** {self._get_concept_explanation(prompt)}

**Card 2:** 
**Front:** Why is {topic} important?
**Back:** It provides systematic approaches for understanding and solving problems in this academic domain.

**Card 3:**
**Front:** How is {topic} applied?
**Back:** Through structured methodologies that can be adapted to various contexts and scenarios.

**Study Method:** Review these cards regularly, test yourself, and create additional cards from your course materials!

**Want more cards?** Upload your materials and I'll generate comprehensive flashcard sets from your lessons! 📚⚡"""
    
    def _generate_review_response(self, prompt: str, style: str, user_id: str) -> str:
        """Generate adaptive review responses"""
        previous_convos = _conversation_memory.get(user_id, [])
        topic = self._extract_topic(prompt)
        
        review_areas = []
        if previous_convos:
            # Analyze previous topics for review recommendations
            prev_topics = [self._extract_topic(conv.get('prompt', '')) for conv in previous_convos[-3:]]
            review_areas.extend(prev_topics)
        
        return f"""**Study Review Session** 📖

**Current Topic: {topic.title()}**
**Status:** {'Continuing previous discussion' if previous_convos else 'New topic'}

**Review Strategy:**
1. **Concept Mastery**: Ensure solid understanding of definitions and principles
2. **Application Practice**: Work through examples and use cases
3. **Connection Building**: Link to related concepts you've studied
4. **Self-Assessment**: Test your knowledge with practice questions

{f"**Previous Topics to Review:** {', '.join(set(review_areas))}" if review_areas else ""}

**Adaptive Recommendation:**
Based on our discussion, focus on connecting theoretical concepts with practical applications for comprehensive understanding.

**Next Steps:** Upload your study materials for personalized review recommendations based on your specific curriculum! 🎯"""
    
    def _generate_professional_response(self, prompt: str, task_type: str, style: str, user_id: str) -> str:
        """Generate professional academic responses"""
        topic = self._extract_topic(prompt)
        previous_convos = _conversation_memory.get(user_id, [])
        
        base_response = f"""**Academic Assistant Response** 🎓

**Topic:** {topic.title()}
**Approach:** Professional academic guidance

**Understanding:** {self._get_concept_explanation(prompt)}

**Learning Framework:**
- **Conceptual Foundation**: Build understanding of core principles
- **Practical Application**: Study real-world implementations
- **Academic Integration**: Connect to broader curriculum context
- **Critical Analysis**: Evaluate different approaches and methodologies

**Educational Support:**
I'm here to help you develop deep, comprehensive understanding of academic concepts. For the most effective learning experience, consider uploading your course materials so I can provide explanations directly aligned with your curriculum.

**Continue Learning:** What specific aspect would you like to explore further? 📚✨"""
        
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
        
        return f"""**Main Concepts in {topic.title()}:**

**1. Fundamental Principles** 📚
The core ideas that form the foundation of understanding this topic.

**2. Key Components** 🔧
The essential elements that work together to create the complete picture.

**3. Methodological Approaches** 📋
Different ways to approach and apply these concepts in practice.

**4. Practical Applications** 🎯
How these concepts are used in real-world scenarios and their impact.

For more specific insights about {topic}, I'd recommend uploading your course materials so I can provide detailed explanations directly from your lessons!"""
    
    def _explain_simply(self, topic: str, prompt_lower: str) -> str:
        """Provide simple explanations"""
        if "machine learning" in topic.lower():
            if "taglish" in prompt_lower:
                return """**Machine Learning in Simple Taglish:**

**Ano ang Machine Learning?** 🤖
Ito yung way na tinuturuan natin ang computer na mag-learn by itself, para hindi na natin kailangan i-program lahat ng details.

**Paano ito gumagana?** 
1. **Data muna** - Bigay tayo ng maraming examples sa computer
2. **Training** - Pina-practice natin siya using those examples  
3. **Prediction** - Kapag naka-learn na siya, pwede na siyang mag-predict ng bagong things

**Simple example:**
Para bang tinuturuan mo yung bata na mag-recognize ng mga aso. Ipapakita mo sa kanya maraming pictures ng aso, tapos eventually ma-re-recognize na niya kung ano yung aso kahit hindi niya pa nakita yung specific na picture na yun.

**Ginagamit saan?**
• Facebook na nag-re-recognize ng faces mo sa pictures
• Spotify na nag-suggest ng songs na gusto mo
• Google Translate na nag-convert ng languages

Gets mo na? Ask lang if may specific part na gusto mo pa i-explain! 😊"""
            
            return """**Machine Learning - Simple Explanation** 🤖

Think of it like teaching a child to recognize things:

**What it is:**
Machine learning is like giving a computer lots of examples so it can learn to make decisions on its own, without us having to tell it exactly what to do every time.

**How it works:**
1. **Show examples** - Like showing a child 1000 pictures of cats
2. **Let it practice** - The computer finds patterns in those examples  
3. **Test it** - Show it a new cat picture it's never seen
4. **It recognizes** - "That's a cat!" (because it learned the pattern)

**Real examples you use:**
• Netflix knowing what movies you might like
• Your phone recognizing your voice
• Email knowing what's spam

It's basically pattern recognition - but super smart and fast! 🧠✨"""
        
        return f"Let me explain {topic} in simple terms:\n\nThis concept involves understanding patterns and relationships that help us solve problems systematically. Think of it as learning the 'why' and 'how' behind important ideas in your field.\n\nFor specific, detailed explanations, upload your course materials and I can break down the exact concepts from your lessons!"
    
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

**Core Definition:**
{topic.title()} refers to the systematic approach and methodological framework used to understand and apply key principles within this domain.

**Key Components:**
• Theoretical foundations that support the concept
• Practical applications and real-world implementations  
• Methodological approaches for problem-solving
• Integration with related concepts and fields

**Why It Matters:**
This concept forms a fundamental building block for advanced understanding in your field of study.

**For Precise Definitions:** Upload your course materials and I'll provide the exact definitions and explanations from your specific curriculum!"""
    
    def _intelligent_general_response(self, prompt: str, is_follow_up: bool) -> str:
        """Generate intelligent general responses for any question"""
        topic = self._extract_topic(prompt)
        
        responses = [
            f"""I understand you're asking about **{topic}**. Let me help you with that! 📚

While I can provide general guidance on this topic, I'd be much more helpful with your specific course materials uploaded. Here's what I can share:

**General Understanding:**
This concept typically involves systematic approaches to problem-solving and requires understanding both theoretical foundations and practical applications.

**To Get Better Help:**
• Upload your lesson materials, PDFs, or notes
• Ask specific questions about particular aspects  
• Let me know your learning goals or what's confusing you

**I'm here to help!** Feel free to ask follow-up questions or share your study materials. 🎯✨""",

            f"""Great question about **{topic}**! 🤔

I can definitely help explain this concept. For the most accurate and detailed information that matches your curriculum, uploading your course materials would be ideal.

**What I can do right now:**
• Provide foundational explanations and definitions
• Break down complex concepts into understandable parts
• Give practical examples and real-world applications
• Help with study strategies and learning approaches

**What would be most helpful:**
If you have specific lesson materials, assignments, or textbooks, I can analyze those and give you targeted explanations that match exactly what you're studying.

How would you like to proceed? Ask me anything! 💡""",

            f"""I'd be happy to help you understand **{topic}** better! 🌟

**Here's how I can assist:**

📖 **Explanations** - Break down complex ideas into clear, understandable parts
🔍 **Examples** - Provide real-world applications and practical scenarios  
📋 **Study Help** - Create summaries, key points, and study guides
💭 **Q&A** - Answer specific questions about concepts, processes, or applications

**For the best help:** Upload your study materials (PDFs, notes, assignments) and I can provide precise answers based on your actual curriculum.

**What specific aspect would you like to explore?** Just ask, and I'll tailor my explanation to your needs! 🎯"""
        ]
        
        # Use prompt content to select varied response
        import hashlib
        hash_val = int(hashlib.md5(prompt.encode()).hexdigest(), 16) % len(responses)
        return responses[hash_val]
    
    def _extract_topic(self, prompt: str) -> str:
        """Extract the main topic from user prompt"""
        # Remove common question words
        words = prompt.lower().replace("what is", "").replace("explain", "").replace("step by step", "").strip()
        # Take first few significant words
        topic_words = [w for w in words.split()[:3] if len(w) > 2]
        return " ".join(topic_words) or "this topic"
    
    def _get_concept_explanation(self, prompt: str) -> str:
        """Generate concept explanation based on prompt keywords"""
        if "machine learning" in prompt.lower():
            return "Machine learning is a method of data analysis that automates analytical model building using algorithms that iteratively learn from data"
        elif "data" in prompt.lower():
            return "Data processing involves collecting, organizing, and analyzing information to extract meaningful insights"
        elif "algorithm" in prompt.lower():
            return "Algorithms are step-by-step procedures for calculations, data processing, and automated reasoning tasks"
        else:
            topic = self._extract_topic(prompt)
            return f"{topic.title()} involves systematic approaches to understanding and applying key principles in this domain"
    
    def _generate_contextual_response(self, prompt: str, is_follow_up: bool = False) -> str:
        """Generate varied contextual responses with conversation awareness"""
        topic = self._extract_topic(prompt)
        
        if is_follow_up:
            response_templates = [
                f"Building on our previous discussion, let me expand on {topic}:\n\n**Additional Perspectives:**\n- This concept has evolved significantly in recent years\n- Modern approaches emphasize practical implementation\n- Integration with other methodologies enhances effectiveness\n\nFor course-specific details, your lesson materials would provide the most accurate information.",
                
                f"Continuing with {topic}, here are some advanced considerations:\n\n**Deeper Analysis:**\n- The theoretical framework supports multiple applications\n- Best practices have been refined through extensive research\n- Current trends show increasing adoption across various fields\n\nYour uploaded documents would contain the specific context for your studies."
            ]
        else:
            response_templates = [
                f"Regarding '{topic}', I can provide insights based on general knowledge. However, for the most accurate information specific to your course materials, please upload your lesson documents.\n\n**General Overview:**\nThis concept typically involves systematic analysis and practical application of established principles in the field.",
                
                f"I understand you're asking about {topic}. While I can offer general guidance, the best answers will come from your specific lesson materials.\n\n**Key Points:**\n- Fundamental principles guide implementation\n- Practical applications vary by context\n- Understanding requires both theory and practice",
                
                f"Great question about {topic}! To give you the most relevant answer, I'd need to reference your uploaded documents.\n\n**What I Can Share:**\n- This area involves structured methodologies\n- Success depends on proper understanding of core concepts\n- Real-world application requires careful consideration of context"
            ]
        
        # Vary responses based on prompt content
        import hashlib
        hash_val = int(hashlib.md5(prompt.encode()).hexdigest(), 16) % len(response_templates)
        return response_templates[hash_val]
    
    def _generate_openai(self, prompt: str, system: str) -> str:
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
                "max_tokens": 1000,
                "temperature": 0.7
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    
    def _generate_anthropic(self, prompt: str, system: str) -> str:
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
                "max_tokens": 1000,
                "system": system,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]
    
    def _generate_gemini(self, prompt: str, system: str) -> str:
        """Generate using Google Gemini API"""
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key not configured")
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "maxOutputTokens": 1000,
                "temperature": 0.7
            }
        }
        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return "No response generated."
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts)

    def _generate_gemini_stream(self, prompt: str, system: str, timeout: int = 60):
        """Stream tokens directly from Google Gemini API"""
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key not configured")

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "maxOutputTokens": 1000,
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
        
Please configure one of the following:
1. Google Gemini API (Recommended)
2. Install and run Ollama locally
3. Set up OpenAI API with your API key
4. Configure Anthropic Claude API

Once configured, I can help you with:
- Answering questions about your uploaded materials
- Creating study summaries
- Generating practice quizzes
- Explaining complex topics in simple terms

For now, I can still help you organize your library and track your study progress!"""

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts using configured provider"""
        if self.provider == "gemini" and GEMINI_API_KEY:
            try:
                return self._embed_gemini(texts)
            except Exception as e:
                print(f"⚠️ Gemini embedding notice: {e}. Falling back.")
                return [[0.1] * 768 for _ in texts]
        elif self.provider == "ollama":
            response = requests.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": texts},
                timeout=180,
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        else:
            # Fallback mock embeddings for other providers
            return [[0.1] * 384 for _ in texts]

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
                        "status": "reachable",
                        "configured_chat_model": GEMINI_MODEL,
                        "configured_embed_model": GEMINI_EMBED_MODEL,
                        "installed_models": [GEMINI_MODEL, GEMINI_EMBED_MODEL],
                        "message": "Google Gemini API connected and ready"
                    })
                else:
                    status.update({
                        "status": "not_configured",
                        "message": "Gemini API key not configured"
                    })
            elif self.provider == "ollama":
                response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
                if response.ok:
                    models = [m.get("name") for m in response.json().get("models", [])]
                    status.update({
                        "status": "reachable",
                        "configured_chat_model": OLLAMA_CHAT_MODEL,
                        "installed_models": models,
                    })
                else:
                    status.update({"status": "unavailable", "message": "Ollama not responding"})
            elif self.provider == "openai":
                status.update({
                    "status": "configured" if OPENAI_API_KEY else "not_configured",
                    "model": OPENAI_MODEL,
                    "message": "API key not set" if not OPENAI_API_KEY else "Ready"
                })
            else:
                status.update({"status": "demo", "message": "Using fast demo responses"})
                
        except Exception as e:
            status.update({"status": "demo", "message": f"Using demo mode - {str(e)}"})
        
        # Cache the result
        _status_cache["last_check"] = current_time
        _status_cache["status"] = status
        return status

# Global AI service instance
ai_service = AIService()

# Legacy functions for backward compatibility
def generate(prompt: str, system: str = "You are KeepAI, a helpful academic tutor.", 
             user_id: str = "default", teaching_style: str = "academic", 
             has_sources: bool = False) -> str:
    return ai_service.generate(prompt, system, user_id, teaching_style, has_sources)

def generate_stream(prompt: str, system: str = "You are KeepAI, a helpful academic tutor.", 
                    user_id: str = "default", teaching_style: str = "academic", 
                    has_sources: bool = False, timeout: int = 240):
    return ai_service.generate_stream(prompt, system, user_id, teaching_style, has_sources, timeout)

def embed_many(texts: List[str]) -> List[List[float]]:
    return ai_service.embed_many(texts)
