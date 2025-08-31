from langchain_google_genai import ChatGoogleGenerativeAI

def create_model():
    return ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.0)