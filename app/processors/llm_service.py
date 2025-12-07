
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from enum import Enum

from app.models.schemas import SummaryMode, LLMBackend
from app.config import settings

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    pass


class BaseLLMService(ABC):
    #abstract base class for LLM services that will define the interface for all LLM backends we define

    @abstractmethod
    def summarize(
        self, 
        text: str, 
        mode: SummaryMode = SummaryMode.BRIEF,
        max_length: Optional[int] = None
    ) -> str:
        # summarize the text
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        # model info
        pass


class OpenAIService(BaseLLMService):
    # use gpt 3.5
    
    def __init__(self, api_key: Optional[str] = None):
        try:
            from openai import OpenAI
        except ImportError:
            raise LLMServiceError(
                "openai package not installed, install it with pip"
            )
        
        self.api_key = api_key or settings.OPENAI_API_KEY
        if not self.api_key:
            raise LLMServiceError(
                "no api key found"
            )
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-3.5-turbo"
        logger.info(f"init openai service with model: {self.model}")
    
    def summarize(
        self, 
        text: str, 
        mode: SummaryMode = SummaryMode.BRIEF,
        max_length: Optional[int] = None
    ) -> str:
        if not text or not text.strip():
            raise LLMServiceError("Cannot summarize empty text")
        
        # build the prompt based on mode
        prompt = self._build_prompt(text, mode, max_length)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that summarizes documents accurately and concisely."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                # Low temp for more focused summaries
                temperature=0.3,  
                max_tokens=self._get_max_tokens(mode, max_length)
            )
            summary = response.choices[0].message.content.strip()
            logger.info(f"Generated {mode.value} summary using openai ({len(summary)} chars)")
            
            return summary
            
        except Exception as e:
            logger.error(f"openai summarization failed: {str(e)}")
            raise LLMServiceError(f"openai API err: {str(e)}")
    
    def _build_prompt(self, text: str, mode: SummaryMode, max_length: Optional[int]) -> str:
        # build the prompt based on summary mode
        
        base_prompt = f"Summarize the following document:\n\n{text}\n\n"
        
        if mode == SummaryMode.BRIEF:
            instruction = "Provide a brief 2-3 sentence summary highlighting ONLY the key points."
        elif mode == SummaryMode.DETAILED:
            instruction = "Provide a detailed summary covering all important aspects of the document."
        elif mode == SummaryMode.BULLET_POINTS:
            instruction = "Provide a summary in bullet points, highlighting the main points."
        else:
            instruction = "Summarize this document concisely."
        
        if max_length:
            instruction += f" Keep the summary under {max_length} words."
        
        return base_prompt + instruction
    
    def _get_max_tokens(self, mode: SummaryMode, max_length: Optional[int]) -> int:
        # determine max tokens based on mode and requested length
        
        if max_length:
            # rough conversion is 1 word approx 1.3 tokens
            return int(max_length * 1.3)
        
        # default token limits by mode
        token_limits = {
            SummaryMode.BRIEF: 150,
            SummaryMode.DETAILED: 500,
            SummaryMode.BULLET_POINTS: 300
        }
        
        return token_limits.get(mode, 300)
    
    def get_model_info(self) -> Dict[str, Any]:
        return {
            "backend": "openai",
            "model": self.model,
            "provider": "openai",
            "description": "GPT-3.5-turbo for high-quality summaries"
        }


class HuggingFaceService(BaseLLMService):
    # use Bart large cnn model from huggingface
    
    def __init__(self, model_name: str = "facebook/bart-large-cnn"):
        try:
            from transformers import pipeline
        except ImportError:
            raise LLMServiceError(
                "transformers package not installed"
            )
        
        self.model_name = model_name
        
        try:
            logger.info(f"Loading Huggingface model: {model_name} (this may take a moment...)")
            self.summarizer = pipeline("summarization", model=model_name)
            logger.info(f"Successfully loaded Huggingface model: {model_name}")
        except Exception as e:
            raise LLMServiceError(f"Failed to load Huggingface model: {str(e)}")
    
    def summarize(
        self, 
        text: str, 
        mode: SummaryMode = SummaryMode.BRIEF,
        max_length: Optional[int] = None
    ) -> str:
        
        if not text or not text.strip():
            raise LLMServiceError("Cannot summarize empty text")
        
        # Huggingface models have token limits around 1024 tokens for BART
        # Truncate if needed rough: 1 token around 4 chars
        max_input_length = 4000  # around 1000 tokens
        if len(text) > max_input_length:
            text = text[:max_input_length]
            logger.warning(f"Truncated input text to {max_input_length} characters")
        
        # Determine length parameters
        min_length, max_output_length = self._get_length_params(mode, max_length, len(text))
        
        try:
            result = self.summarizer(
                text,
                min_length=min_length,
                max_length=max_output_length,
                do_sample=False  # Deterministic output
            )
            
            summary = result[0]['summary_text'].strip()
            
            # For bullet points mode, format the summary
            if mode == SummaryMode.BULLET_POINTS:
                summary = self._format_as_bullets(summary)
            
            logger.info(f"Generated {mode.value} summary using Huggingface ({len(summary)} chars)")
            
            return summary
            
        except Exception as e:
            logger.error(f"Huggingface summarization failed: {str(e)}")
            raise LLMServiceError(f"Huggingface error: {str(e)}")
    
    def _get_length_params(
        self, 
        mode: SummaryMode, 
        max_length: Optional[int],
        text_length: int
    ) -> tuple[int, int]:
        # calculate the minmax length param for the hf model
        
        # Default ranges by mode (in tokens, roughly 4 chars per token)
        if mode == SummaryMode.BRIEF:
            min_len, max_len = 30, 60
        elif mode == SummaryMode.DETAILED:
            min_len, max_len = 100, 200
        elif mode == SummaryMode.BULLET_POINTS:
            min_len, max_len = 50, 100
        else:
            min_len, max_len = 50, 100
        
        # Override if max_length specified
        if max_length:
            # Convert words to approximate tokens
            max_len = min(max_length, 200)  # Cap at 200 tokens
            min_len = min(min_len, max_len // 2)
        
        return min_len, max_len
    
    def _format_as_bullets(self, text: str) -> str:
        # Split on sentences and convert to bullets
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        
        if len(sentences) <= 1:
            return f"• {text}"
        
        return '\n'.join([f"• {sentence}." for sentence in sentences])
    
    def get_model_info(self) -> Dict[str, Any]:
        return {
            "backend": "huggingface",
            "model": self.model_name,
            "provider": "Huggingface",
            "description": "Local summarization model (free)"
        }


class LLMServiceFactory:
    
    @staticmethod
    def create(backend: LLMBackend) -> BaseLLMService:

        #Create an LLM service instance
        if backend == LLMBackend.OPENAI:
            return OpenAIService()
        elif backend == LLMBackend.HUGGINGFACE:
            return HuggingFaceService()
        else:
            raise LLMServiceError(f"Unknown backend: {backend}")
    
    @staticmethod
    def get_available_backends() -> list[str]:
        #Get list of available backends
        return [backend.value for backend in LLMBackend]