"""
Multilingual Language Service for AI Chatbot.
Supports: English, Traditional Chinese (zh-TW), Simplified Chinese (zh-CN)
"""
import re
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class LanguageCode:
    """Language code constants."""
    ENGLISH = 'en'
    SIMPLIFIED_CHINESE = 'zh-CN'
    TRADITIONAL_CHINESE = 'zh-TW'
    
    SUPPORTED = [ENGLISH, SIMPLIFIED_CHINESE, TRADITIONAL_CHINESE]
    
    DISPLAY_NAMES = {
        ENGLISH: 'English',
        SIMPLIFIED_CHINESE: '简体中文 (Simplified Chinese)',
        TRADITIONAL_CHINESE: '繁體中文 (Traditional Chinese)',
    }


class LanguageService:
    """
    Service for language detection and multilingual support.
    Detects user's language and provides localized response templates.
    """
    
    # Common Chinese characters that differ between Simplified and Traditional
    # Simplified-only characters (not in Traditional)
    SIMPLIFIED_ONLY = set('与业两严东丝临为义乌书亚产从众优会传伤体余佣信们备处复够头夸奋妇嫩学实审寻对导专尔尘层属岁币师帮并广应张当录彻总执扩护报拟择击拥挤换损据时旧显晓晚晨普暴术权来极构标样档梦检欢气汇汉汤汹沟济浅浆测满滚潜灰灾炉点犹狭独玛环现璃电疏网罗罚罢胜节苏药虽虾蚂蚕见观规览认证识词诉试话误请诸读调资赋购车软达运违连远迟选遣释里铁锁问闪阴阵阶随险难雪零雾需韩页预颍风飞饰骂鱼鸡麦鼓齿龙龟')
    
    # Traditional-only characters (not in Simplified)
    TRADITIONAL_ONLY = set('與業兩嚴東絲臨為義烏書亞產從眾優會傳傷體餘佣僅們備處復夠頭誇奮婦嫩學實審尋對導專爾塵層屬歲幣師幫並廣應張當錄徹總執擴護報擬擇擊擁擠換損據時舊顯曉晚晨普暴術權來極構標樣檔夢檢歡氣彙漢湯洶溝濟淺漿測滿滾潛灰災爐點猶狹獨瑪環現璃電疏網羅罰罷勝節蘇藥雖蝦螞蠶見觀規覽認證識詞訴試話誤請諸讀調資賦購車軟達運違連遠遲選遣釋裡鐵鎖問閃陰陣階隨險難雪零霧需韓頁預潁風飛飾駡魚雞麥鼓齒龍龜')
    
    # Common greeting patterns by language
    ENGLISH_GREETINGS = [
        r'\bhello\b', r'\bhi\b', r'\bhey\b', r'\bgood\s*(morning|afternoon|evening)\b',
        r'\bhow\s+are\s+you\b', r'\bwhat\'s\s+up\b', r'\bhowdy\b', r'\bgreetings\b'
    ]
    
    CHINESE_GREETINGS = [
        r'你好', r'您好', r'嗨', r'哈囉', r'早安', r'早上好', r'下午好', r'晚上好',
        r'晚安', r'请问', r'請問', r'我想', r'想问', r'想問', r'怎么样', r'怎麼樣',
        r'好久不见', r'好久不見'
    ]
    
    # Response templates for different scenarios
    RESPONSE_TEMPLATES = {
        LanguageCode.ENGLISH: {
            'greeting': "Hello! I'm AI Assistant, your AI assistant for {business_name}. How can I help you today?",
            'handoff': "I'll connect you with a team member who can help you better.",
            'error': "I apologize, but I'm having trouble processing your request. Let me connect you with a team member.",
            'no_info': "I don't have specific information about that. Let me connect you with our team for accurate details.",
            'booking_intro': "I'd be happy to help you make a reservation! Please let me know:",
            'booking_date': "What date would you like to make a reservation for?",
            'booking_time': "What time would you prefer?",
            'booking_party_size': "How many guests will be dining?",
            'booking_name': "May I have your name for the reservation?",
            'booking_phone': "And a phone number to confirm the booking?",
            'booking_confirm': "Great! I've noted your reservation for {party_size} guests on {date} at {time}. We'll confirm shortly!",
            'property_intro': "I can help you find the perfect property! Are you looking to buy or rent?",
            'lead_budget': "What's your budget range?",
            'lead_area': "Which areas are you interested in?",
            'lead_timeline': "When are you looking to move?",
            'thank_you': "Thank you! Is there anything else I can help you with?",
        },
        LanguageCode.SIMPLIFIED_CHINESE: {
            'greeting': "您好！我是 AI 助理，{business_name} 的智能客服。请问有什么可以帮您的吗？",
            'handoff': "我将为您转接人工客服，以便更好地为您服务。",
            'error': "抱歉，我在处理您的请求时遇到了问题。让我为您转接人工客服。",
            'no_info': "关于这个问题，我没有具体的信息。让我为您转接我们的团队以获取准确的详情。",
            'booking_intro': "很高兴为您预订！请告诉我：",
            'booking_date': "您想预订哪一天？",
            'booking_time': "您希望什么时间？",
            'booking_party_size': "请问几位用餐？",
            'booking_name': "请问您贵姓？",
            'booking_phone': "请留下您的联系电话以便确认预订？",
            'booking_confirm': "好的！已为您记录 {date} {time} {party_size} 位的预订。我们会尽快确认！",
            'property_intro': "我可以帮您找到理想的房产！您是想买房还是租房？",
            'lead_budget': "您的预算范围是多少？",
            'lead_area': "您对哪些区域感兴趣？",
            'lead_timeline': "您计划什么时候搬家？",
            'thank_you': "谢谢！还有其他可以帮您的吗？",
        },
        LanguageCode.TRADITIONAL_CHINESE: {
            'greeting': "您好！我是 AI 助理，{business_name} 的智能客服。請問有什麼可以幫您的嗎？",
            'handoff': "我將為您轉接人工客服，以便更好地為您服務。",
            'error': "抱歉，我在處理您的請求時遇到了問題。讓我為您轉接人工客服。",
            'no_info': "關於這個問題，我沒有具體的資訊。讓我為您轉接我們的團隊以獲取準確的詳情。",
            'booking_intro': "很高興為您預訂！請告訴我：",
            'booking_date': "您想預訂哪一天？",
            'booking_time': "您希望什麼時間？",
            'booking_party_size': "請問幾位用餐？",
            'booking_name': "請問您貴姓？",
            'booking_phone': "請留下您的聯繫電話以便確認預訂？",
            'booking_confirm': "好的！已為您記錄 {date} {time} {party_size} 位的預訂。我們會盡快確認！",
            'property_intro': "我可以幫您找到理想的房產！您是想買房還是租房？",
            'lead_budget': "您的預算範圍是多少？",
            'lead_area': "您對哪些區域感興趣？",
            'lead_timeline': "您計劃什麼時候搬家？",
            'thank_you': "謝謝！還有其他可以幫您的嗎？",
        }
    }
    
    # System prompt additions for each language
    LANGUAGE_INSTRUCTIONS = {
        LanguageCode.ENGLISH: """
LANGUAGE: The customer is communicating in ENGLISH.
You MUST respond entirely in English.
""",
        LanguageCode.SIMPLIFIED_CHINESE: """
语言要求：客户正在使用【简体中文】进行沟通。
您必须完全使用简体中文回复。
请使用自然、友好的中文表达方式。
注意：使用简体字，不要使用繁体字。
""",
        LanguageCode.TRADITIONAL_CHINESE: """
語言要求：客戶正在使用【繁體中文】進行溝通。
您必須完全使用繁體中文回覆。
請使用自然、友好的中文表達方式。
注意：使用繁體字，不要使用簡體字。
"""
    }
    
    @classmethod
    def detect_language(cls, text: str) -> str:
        """
        Detect the language of the input text.
        Returns: Language code (en, zh-CN, zh-TW)
        """
        if not text or not text.strip():
            return LanguageCode.ENGLISH
        
        text = text.strip()
        
        # Check for Chinese characters
        chinese_chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
        total_chars = len([c for c in text if c.isalpha() or '\u4e00' <= c <= '\u9fff'])
        
        if total_chars == 0:
            return LanguageCode.ENGLISH
        
        chinese_ratio = len(chinese_chars) / total_chars if total_chars > 0 else 0
        
        # If mostly Chinese (>30% Chinese characters), determine which variant
        if chinese_ratio > 0.3 or len(chinese_chars) >= 2:
            return cls._distinguish_chinese_variant(text)
        
        # Default to English
        return LanguageCode.ENGLISH
    
    @classmethod
    def _distinguish_chinese_variant(cls, text: str) -> str:
        """
        Distinguish between Simplified and Traditional Chinese.
        """
        simplified_count = sum(1 for c in text if c in cls.SIMPLIFIED_ONLY)
        traditional_count = sum(1 for c in text if c in cls.TRADITIONAL_ONLY)
        
        if traditional_count > simplified_count:
            return LanguageCode.TRADITIONAL_CHINESE
        elif simplified_count > traditional_count:
            return LanguageCode.SIMPLIFIED_CHINESE
        else:
            # If equal or no distinguishing characters, use heuristics
            # Check for common Traditional-only patterns
            traditional_patterns = ['請', '這', '裡', '東', '來', '個', '們', '會', '對', '時']
            simplified_patterns = ['请', '这', '里', '东', '来', '个', '们', '会', '对', '时']
            
            trad_matches = sum(1 for p in traditional_patterns if p in text)
            simp_matches = sum(1 for p in simplified_patterns if p in text)
            
            if trad_matches > simp_matches:
                return LanguageCode.TRADITIONAL_CHINESE
            elif simp_matches > trad_matches:
                return LanguageCode.SIMPLIFIED_CHINESE
            else:
                # Default to Simplified if can't determine
                return LanguageCode.SIMPLIFIED_CHINESE
    
    @classmethod
    def get_template(cls, language: str, template_key: str, **kwargs) -> str:
        """
        Get a localized template string.
        """
        if language not in cls.RESPONSE_TEMPLATES:
            language = LanguageCode.ENGLISH
        
        templates = cls.RESPONSE_TEMPLATES.get(language, cls.RESPONSE_TEMPLATES[LanguageCode.ENGLISH])
        template = templates.get(template_key, '')
        
        if template and kwargs:
            try:
                return template.format(**kwargs)
            except KeyError:
                return template
        return template
    
    @classmethod
    def get_language_instruction(cls, language: str) -> str:
        """
        Get the language instruction to add to the system prompt.
        """
        return cls.LANGUAGE_INSTRUCTIONS.get(language, cls.LANGUAGE_INSTRUCTIONS[LanguageCode.ENGLISH])
    
    @classmethod
    def get_greeting_for_language(cls, language: str, business_name: str) -> str:
        """
        Get the appropriate greeting for a language.
        """
        return cls.get_template(language, 'greeting', business_name=business_name)
    
    @classmethod
    def get_handoff_message(cls, language: str) -> str:
        """
        Get the handoff message in the appropriate language.
        """
        return cls.get_template(language, 'handoff')
    
    @classmethod
    def get_error_message(cls, language: str) -> str:
        """
        Get the error message in the appropriate language.
        """
        return cls.get_template(language, 'error')
    
    @classmethod
    def is_greeting(cls, text: str) -> bool:
        """
        Check if the text is a greeting in any supported language.
        """
        text_lower = text.lower().strip()
        
        # Check English greetings
        for pattern in cls.ENGLISH_GREETINGS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        
        # Check Chinese greetings
        for pattern in cls.CHINESE_GREETINGS:
            if pattern in text:
                return True
        
        return False
    
    @classmethod
    def get_multilingual_prompt_section(cls, detected_language: str, business_name: str) -> str:
        """
        Generate the multilingual section of the system prompt.
        """
        language_instruction = cls.get_language_instruction(detected_language)
        greeting_example = cls.get_greeting_for_language(detected_language, business_name)
        handoff_msg = cls.get_handoff_message(detected_language)
        
        prompt = f"""
{language_instruction}

GREETING RESPONSE FOR THIS LANGUAGE:
When customer greets, respond with:
"{greeting_example}"

HANDOFF MESSAGE FOR THIS LANGUAGE:
When uncertain or escalating, say:
"{handoff_msg}"
"""
        return prompt
    
    @classmethod
    def get_language_display_name(cls, language_code: str) -> str:
        """
        Get the display name for a language code.
        """
        return LanguageCode.DISPLAY_NAMES.get(language_code, 'English')


# Convenience functions for easy access
def detect_language(text: str) -> str:
    """Detect the language of the given text."""
    return LanguageService.detect_language(text)


def get_localized_response(language: str, template_key: str, **kwargs) -> str:
    """Get a localized response template."""
    return LanguageService.get_template(language, template_key, **kwargs)
