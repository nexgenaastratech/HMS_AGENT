
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Hotel Harriet Chatbot"
    VERSION: str = "v21.0"
    API_V1_STR: str = "/api/v1"
    
    # WhatsApp Config
    VERIFY_TOKEN: str = os.getenv("VERIFY_TOKEN")
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN")
    PHONE_NUMBER_ID: str = os.getenv("PHONE_NUMBER_ID")
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
    APP_SECRET: str = os.getenv("APP_SECRET")
    
    # AI Keys
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY")

    # Azure OpenAI Config
    AZURE_OPENAI_KEY: str = os.getenv("AZURE_OPENAI_KEY")
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION")
    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME: str = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4o-mini")
    AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME: str = os.getenv("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT_NAME", "text-embedding-3-small")

    
    # Hotel & Flow Config
    HOTEL_HARRIET_TOKEN: str = os.getenv("HOTEL_HARRIET_TOKEN")
    FLOW_ID: str = os.getenv("FLOW_ID")
    FLOW_ID_SERVICE: str = os.getenv("FLOW_ID_SERVICE")
    
    # HMS Auth
    HMS_BASE_URL: str = os.getenv("HMS_BASE_URL")
    HMS_LOGIN_URL: str = f"{HMS_BASE_URL}/api/Login/Login"
    HMS_USERNAME: str = os.getenv("HMS_USERNAME")
    HMS_PASSWORD: str = os.getenv("HMS_PASSWORD")
    HMS_CHANNEL_ID: int = int(os.getenv("HMS_CHANNEL_ID", "0") or "0")
    
    # Internal Security
    API_KEY: str = os.getenv("API_KEY")
    SECRET_KEY: str = os.getenv("SECRET_KEY")

    
    # URLs / Assets
    TOURIST_WEBSITE_URL: str = os.getenv("TOURIST_WEBSITE_URL")
    TOURIST_HERO_IMAGE: str = os.getenv("TOURIST_HERO_IMAGE")
    CHAT_LOG_URL: str = f"{HMS_BASE_URL}/api/ChatBot/AddChat"
    NOTIFICATION_URL: str = f"{HMS_BASE_URL}/api/QueryRequest/CreateQueryRequest"
    ROOM_LIST_URL: str = f"{HMS_BASE_URL}/api/QueryRequest/GetRoomsByMobile"
    GET_ALL_QUERY_REQUEST_URL: str = f"{HMS_BASE_URL}/api/QueryRequest/GetAllQueryRequest"
    CHANGE_TO_COMPLETED_URL: str = f"{HMS_BASE_URL}/api/QueryRequest/ChangeToCompleted"
    SPECIAL_REQUEST_URL: str = f"{HMS_BASE_URL}/api/QueryRequest/CreateQueryRequest"
    CHECK_RESERVED_STATUS_URL: str = f"{HMS_BASE_URL}/api/Booking/CheckReservedStatus"
    ADD_SPECIAL_REQUEST_URL: str = f"{HMS_BASE_URL}/api/QueryRequest/AddSpecialRequest"
    
    # Database
    SQL_SERVER_CONN: str = os.getenv("SQL_SERVER_CONN")
    # Celery & Upstash
    REDIS_URL: str = os.getenv("REDIS_URL")
    FOLLOWUP_COUNTDOWN_SECONDS: int = int(os.getenv("FOLLOWUP_COUNTDOWN_SECONDS", "30"))
    INITIAL_FOLLOWUP_DELAY_SECONDS: int = int(os.getenv("INITIAL_FOLLOWUP_DELAY_SECONDS", "10"))
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "")
 
 

settings = Settings()
