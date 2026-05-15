import re
from typing import Tuple

class MessageFilter:
    # Enhanced regular expressions for detecting contact information
    PHONE_PATTERN = r"""
        (?:(?:\+?\d{1,3}[-.\s]?)?   # Optional country code
        \(?\d{3}\)?[-.\s]?          # Area code
        \d{3}[-.\s]?\d{4})          # Rest of the number
        |
        \b(?:one|two|three|four|five|six|seven|eight|nine|zero|oh)
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)?
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)?
        (?:\s|-)*
        (?:one|two|three|four|five|six|seven|eight|nine|zero|oh)?
    """
    
    EMAIL_PATTERN = r"""
        [\w\.-]+
        \s*(?:@|\(at\))\s*
        [\w\.-]+
        \s*(?:\.|\(dot\))\s*
        \w+
    """
    
    SOCIAL_PATTERN = r"""
        (?:(?:https?:)?//)?        # Optional protocol
        (?:www\.)?                 # Optional www
        (?:                        # Start social media domains
            facebook\.com|
            fb\.com|
            twitter\.com|
            instagram\.com|
            linkedin\.com|
            t\.me|                 # Telegram
            wa\.me                 # WhatsApp
        )
        /[\w\.-]+                  # Username or path
    """

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        """
        Normalize text to handle obfuscation.
        """
        text = text.lower()
        
        # Convert spelled-out numbers to digits
        num_words = {
            "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
            "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
            "oh": "0"
        }
        for word, digit in num_words.items():
            text = text.replace(word, digit)
            
        # Handle character substitutions
        substitutions = {
            "(at)": "@", "(dot)": ".", "[at]": "@", "[dot]": "."
        }
        for old, new in substitutions.items():
            text = text.replace(old, new)
            
        return text

    @classmethod
    def contains_contact_info(cls, text: str) -> Tuple[bool, str]:
        """
        Check if text contains any contact information.
        Returns (contains_info, type_of_info)
        """
        normalized_text = cls._normalize_text(text)
        
        if re.search(cls.PHONE_PATTERN, normalized_text, re.VERBOSE | re.IGNORECASE):
            return True, "phone number"
        
        if re.search(cls.EMAIL_PATTERN, normalized_text, re.VERBOSE | re.IGNORECASE):
            return True, "email address"
        
        if re.search(cls.SOCIAL_PATTERN, text, re.VERBOSE | re.IGNORECASE):
            return True, "social media link"
            
        return False, ""

    @classmethod
    def filter_message(cls, text: str) -> Tuple[str, bool]:
        """
        Filter out contact information from message.
        Returns (filtered_text, was_modified)
        """
        original = text
        
        # Replace phone numbers
        text = re.sub(cls.PHONE_PATTERN, "[PHONE NUMBER REMOVED]", text, 
                     flags=re.VERBOSE | re.IGNORECASE)
        
        # Replace email addresses
        text = re.sub(cls.EMAIL_PATTERN, "[EMAIL REMOVED]", text, 
                     flags=re.VERBOSE | re.IGNORECASE)
        
        # Replace social media links
        text = re.sub(cls.SOCIAL_PATTERN, "[SOCIAL MEDIA LINK REMOVED]", text, 
                     flags=re.VERBOSE | re.IGNORECASE)
        
        was_modified = original != text
        return text, was_modified
