import json
import os
import random
import sys
from typing import Dict, List, Optional
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

class KeepAITrainingService:
    """
    Professional training service that uses the KeepAI training dataset
    to improve AI responses and provide specialized academic assistance
    """
    
    def __init__(self):
        self.dataset_path = Path(__file__).parent.parent.parent / "KeepAI_Training_Dataset"
        self.training_examples = []
        self.knowledge_base = {}
        self.task_patterns = {}
        self.load_training_data()
        self.load_knowledge_base()
    
    def load_training_data(self):
        """Load and process the training dataset"""
        train_file = self.dataset_path / "datasets" / "keepai_train.jsonl"
        
        if not train_file.exists():
            print(f"Training dataset not found at {train_file}")
            return
        
        try:
            with open(train_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        example = json.loads(line.strip())
                        self.training_examples.append(example)
                        
                        # Organize by task type
                        task = example.get('metadata', {}).get('task', 'unknown')
                        if task not in self.task_patterns:
                            self.task_patterns[task] = []
                        self.task_patterns[task].append(example)
            
            print(f"✅ Loaded {len(self.training_examples)} training examples")
            print(f"📊 Task types: {list(self.task_patterns.keys())}")
            
        except Exception as e:
            print(f"❌ Error loading training data: {e}")
    
    def load_knowledge_base(self):
        """Load the knowledge base documents"""
        kb_path = self.dataset_path / "knowledge_base"
        
        if not kb_path.exists():
            return
        
        for file_path in kb_path.glob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.knowledge_base[file_path.stem] = content
                    
            except Exception as e:
                print(f"❌ Error loading knowledge base {file_path}: {e}")
        
        print(f"📚 Loaded knowledge base: {list(self.knowledge_base.keys())}")
    
    def get_training_prompt(self, task_type: str, style: str = "academic") -> Optional[str]:
        """Get a relevant training prompt for the given task type"""
        if task_type not in self.task_patterns:
            return None
        
        # Find examples matching the style
        matching_examples = [
            ex for ex in self.task_patterns[task_type]
            if ex.get('metadata', {}).get('style', 'academic') == style
        ]
        
        if not matching_examples:
            matching_examples = self.task_patterns[task_type]
        
        if matching_examples:
            example = random.choice(matching_examples)
            return example.get('instruction', '')
        
        return None
    
    def get_example_response(self, task_type: str, input_text: str) -> Optional[Dict]:
        """Get an example response pattern for the given task and input"""
        if task_type not in self.task_patterns:
            return None
        
        # Find similar examples
        examples = self.task_patterns[task_type]
        
        # Simple similarity based on keyword overlap
        input_words = set(input_text.lower().split())
        best_match = None
        best_score = 0
        
        for example in examples:
            example_words = set(example.get('input', '').lower().split())
            score = len(input_words.intersection(example_words))
            if score > best_score:
                best_score = score
                best_match = example
        
        return best_match
    
    def enhance_system_prompt(self, base_prompt: str, task_type: str, style: str = "academic") -> str:
        """Enhance system prompt with training-based instructions"""
        training_prompt = self.get_training_prompt(task_type, style)
        
        if training_prompt:
            return f"{training_prompt}\n\nAdditional context: {base_prompt}"
        
        return base_prompt
    
    def get_rag_guidance(self) -> str:
        """Get RAG guidance from knowledge base"""
        return self.knowledge_base.get('keepai_rag_guidance', '')
    
    def detect_task_type(self, user_input: str) -> str:
        """Detect the task type based on user input"""
        user_lower = user_input.lower()
        
        # Task detection patterns
        task_indicators = {
            'quiz_generation': ['quiz', 'test', 'questions', 'exam', 'multiple choice'],
            'tutor_explanation': ['explain', 'what is', 'how does', 'define', 'describe'],
            'summarization': ['summarize', 'summary', 'key points', 'main ideas'],
            'flashcard_generation': ['flashcard', 'cards', 'memorize', 'recall'],
            'adaptive_review': ['review', 'study', 'practice', 'prepare'],
            'mistake_explanation': ['wrong', 'mistake', 'error', 'correct', 'fix']
        }
        
        for task, indicators in task_indicators.items():
            if any(indicator in user_lower for indicator in indicators):
                return task
        
        return 'tutor_explanation'  # default
    
    def get_style_preference(self, teaching_style: str) -> str:
        """Map teaching style to dataset style"""
        style_mapping = {
            'simple': 'taglish',
            'beginner': 'taglish', 
            'examples': 'academic',
            'professor': 'professor',
            'step-by-step': 'academic',
            'taglish': 'taglish',
            'socratic': 'academic',
            'detailed': 'professor',
            'visual': 'academic'
        }
        
        return style_mapping.get(teaching_style, 'academic')
    
    def generate_enhanced_response(self, user_input: str, teaching_style: str = "academic", 
                                 context: str = "", has_sources: bool = False) -> Dict:
        """Generate enhanced response using training data patterns"""
        
        # Detect task type
        task_type = self.detect_task_type(user_input)
        style = self.get_style_preference(teaching_style)
        
        # Get example pattern
        example = self.get_example_response(task_type, user_input)
        
        # Build enhanced response info
        response_info = {
            'task_type': task_type,
            'style': style,
            'has_training_pattern': example is not None,
            'example_pattern': example,
            'enhanced_instruction': self.get_training_prompt(task_type, style) or "",
            'rag_guidance': self.get_rag_guidance() if has_sources else "",
        }
        
        return response_info

# Global training service instance
training_service = KeepAITrainingService()