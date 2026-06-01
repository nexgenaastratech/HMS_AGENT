import os
import shutil
from langchain_openai import AzureChatOpenAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from app.core.config import settings
from pypdf import PdfReader
import logging
import threading
import time

class RAGSystem:
    _instance_lock = threading.Lock()
    _is_initialized = False
    def __init__(self):
        if not settings.GOOGLE_API_KEY:
             logging.warning(" GOOGLE_API_KEY is missing! RAG System may fail.")

        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.GOOGLE_API_KEY
        )
        
        self.vector_store = None
        
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=400)
        
        self.llm = AzureChatOpenAI(
            azure_deployment=settings.AZURE_OPENAI_CHAT_DEPLOYMENT_NAME,
            openai_api_key=settings.AZURE_OPENAI_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            temperature=1
        )

    def _safe_add_documents(self, chunks):
        """Adds documents to the vector store with retry logic for 429 errors."""
        max_retries = 3
        retry_delay = 10  # Seconds to wait on 429
        
        for attempt in range(max_retries):
            try:
                if self.vector_store is None:
                    self.vector_store = FAISS.from_documents(chunks, self.embeddings)
                else:
                    self.vector_store.add_documents(chunks)
                return True
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    logging.warning(f"Rate limit hit during embedding. Attempt {attempt+1}/{max_retries}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logging.error(f"Failed to add documents: {e}")
                    raise e
        return False

    def add_text(self, text: str):
        if not text:
            return
        
        self.index_path = "faiss_index"
        docs = [Document(page_content=text)]
        chunks = self.text_splitter.split_documents(docs)
        
        if not chunks: 
            logging.warning("No chunks created from text.")
            return

        try:
            success = self._safe_add_documents(chunks)
            if success:
                logging.info(f"Successfully indexed {len(chunks)} chunks. Total: {self.vector_store.index.ntotal}")
                # Persist index immediately
                self.vector_store.save_local(self.index_path)
            else:
                logging.error("Final attempt to index chunks failed.")
        except Exception as e:
            logging.error(f"Error in add_text: {e}")

    def add_file(self, file_path: str):
        """Extracts text from a file and adds it to the vector store."""
        text = ""
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext == ".pdf":
                reader = PdfReader(file_path)
                for page in reader.pages:
                    content = page.extract_text()
                    if content:
                        text += content + "\n"
            elif ext in [".txt", ".md", ".csv", ".xml"]:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
            
            if text:
                self.add_text(text)
                print(f"Loaded: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"Failed to load {file_path}: {e}")

    def initialize_knowledge_base(self):
        """
        Initializes the knowledge base. 
        Uses a lock to prevent multiple workers from initializing at the same time.
        """
        with self._instance_lock:
            if self.vector_store and self.vector_store.index.ntotal > 0:
                return

            self.index_path = "faiss_index"
            
            # 1. Try to load existing Index
            if os.path.exists(os.path.join(self.index_path, "index.faiss")):
                try:
                    self.vector_store = FAISS.load_local(
                        self.index_path, 
                        self.embeddings, 
                        allow_dangerous_deserialization=True
                    )
                    if self.vector_store and self.vector_store.index.ntotal > 0:
                        print(f"Loaded existing FAISS index from {self.index_path} ({self.vector_store.index.ntotal} vectors)")
                        return # EXIT EARLY - DB IS READY
                    else:
                        print("Existing index is empty. Re-initializing...")
                except Exception as e:
                    print(f"Failed to load existing index: {e}")
        
        # 2. Create New Index (Only enters here if DB is missing or load failed)
        print("Initializing new Knowledge Base (This may take a moment)...")
        
        sources_dir = os.path.join(os.getcwd(), "vector_db")
        if not os.path.exists(sources_dir):
            print(f"Error: Directory {sources_dir} not found.")
            return

        print(f"Loading documents from {sources_dir}...")
        doc_count = 0
        for file in sorted(os.listdir(sources_dir)): # Sorted for predictable order
            file_path = os.path.join(sources_dir, file)
            # ONLY index Hotel related documents. Keep transportation out of RAG.
            if os.path.isfile(file_path) and ("hotel" in file.lower() or "pdf" in file.lower()):
                 self.add_file(file_path)
                 doc_count += 1
                 time.sleep(2.0) # Increased delay to prevent 429 rate limits
        
        if self.vector_store:
            try:
                # 3. SAVE THE INDEX SO WE DON'T RE-INDEX EVERY TIME
                self.vector_store.save_local(self.index_path)
                
                # Get number of vectors
                total_docs = self.vector_store.index.ntotal
                print(f"Indexing complete. Total vectors in FAISS: {total_docs}")
                logging.info(f"RAG System initialized and SAVED with {total_docs} vectors from {doc_count} files.")
            except Exception as e:
                logging.error(f"Error checking vector count or saving: {e}")

    def get_context(self, query: str, history: list = None):
        """
        Retrieves context and returns an AI-generated answer.
        Matching the signature expected by bot.py.
        """
        if not query:
            return ""
            
        if not self.vector_store:
            self.initialize_knowledge_base()
        
        if not self.vector_store:
             return "I don't have that specific information in my database right now."

        standalone_query = query
        
        # 0. Contextual Rephrasing (If history exists)
        if history and len(history) > 1:
            try:
                history_text = "\n".join(
                    [f"{m['role'].upper()}: {m['content']}" for m in history[-5:]]
                )

                rephrase_prompt = f"""
                You are a travel query rewriter for the 'Harriet Guide Bot'.
                
                Analyze the conversation history and the follow-up question.
                
                Rules:
                1. If the user asks about traveling, routes, or how to reach Rameswaram, rewrite the query to include the Origin City AND mention "Train, Bus, Flight, and Hotel Harriet".
                2. If the question is specifically about HOTEL HARRIET (amenities, price, food, complaints), ensure the query focuses on the hotel.
                3. If the user mentions a location (e.g., "from Bangalore"), ALWAYS include that origin in the search query.
                4. Output ONLY a standalone search query that covers all possible modes of transport to get the best info.
                5. Do NOT include explanations, labels, or extra text.

                Conversation History:
                {history_text}

                Follow-up Question:
                {query}

                Standalone Search Query:
                """
                
                # Use a small retry for rephrasing too
                for _ in range(2):
                    try:
                        rephrase_response = self.llm.invoke(rephrase_prompt)
                        standalone_query = rephrase_response.content.strip()
                        break
                    except Exception:
                        time.sleep(2)
                
                logging.info(f"Rephrased: {query} -> {standalone_query}")
            except Exception as re_e:
                logging.error(f"Failed to rephrase: {re_e}")

        # 1. Retrieve Context ONLY for Hotel Information using LLM Intent Classification
        intent_prompt = f"""
        Analyze the following user query and determine if it requires specific knowledge about a hotel's facilities, rooms, amenities, policies, pricing, booking, or the hotel stay itself.
        
        Answer EXACTLY and ONLY with 'YES' if it requires hotel knowledge.
        Answer EXACTLY and ONLY with 'NO' if it is a general question, a travel/transport inquiry outside the hotel, a generic greeting, or off-topic.
        
        User Query: "{standalone_query}"
        Answer:
        """
        
        is_hotel_query = False
        try:
            intent_response = self.llm.invoke(intent_prompt)
            intent_text = intent_response.content.strip().upper()
            is_hotel_query = 'YES' in intent_text
            logging.info(f"LLM Intent Classification for '{standalone_query}': {intent_text} -> is_hotel: {is_hotel_query}")
        except Exception as e:
            logging.error(f"Failed to classify intent with LLM: {e}")
            # Fallback to robust keyword matching if LLM fails
            hotel_keywords = ["hotel", "room", "amenity", "breakfast", "wifi", "price", "booking", "check-in", "check-out", "checkout", "availability", "stay", "Harriet", "sleep", "wash", "bed", "eat", "food"]
            is_hotel_query = any(k.lower() in standalone_query.lower() for k in hotel_keywords)
            logging.info(f"Fallback Keyword Classification for '{standalone_query}': is_hotel: {is_hotel_query}")

        context_text = ""
        if is_hotel_query:
            max_retries = 3
            retry_delay = 5
            results = []
            
            for attempt in range(max_retries):
                try:
                    # Ensure we have an index
                    if not self.vector_store or self.vector_store.index.ntotal == 0:
                         self.initialize_knowledge_base()
                    
                    if self.vector_store:
                        # Extract chunks specifically about the hotel
                        results = self.vector_store.similarity_search(standalone_query, k=8)
                        logging.info(f"Retrieved {len(results)} hotel-specific chunks.")
                        context_text = "\n\n".join([doc.page_content for doc in results])
                        break
                except Exception as e:
                    error_str = str(e)
                    if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < max_retries - 1:
                        logging.warning(f"Search rate limit hit. Retrying in {retry_delay}s... ({attempt+1}/{max_retries})")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logging.error(f"Similarity search failed: {e} proceeding with empty context")
                        context_text = ""
                        break
        else:
             logging.info("Skipping RAG for non-hotel/travel query. AI will answer directly.")
        
        # If it was a hotel query but no context found
        if is_hotel_query and (not context_text or context_text.strip() == ""):
            logging.warning(f"No hotel context found for: {standalone_query}")
            # We don't return here because we want the model to still answer if it's travel-related
        
        # 2. Generate Answer — TWO DISTINCT PATHS
        max_retries = 3
        retry_delay = 5
        final_query = standalone_query if history else query

        if is_hotel_query:
            # ===== PATH A: HOTEL / TRAVEL — Uses RAG context =====
            logging.info(f"[RAG PATH] Generating hotel answer using context ({len(context_text)} chars)...")
            prompt_template = ChatPromptTemplate.from_template("""You are 'Harriet Guide Bot' \U0001f3e8.
Your goal is to provide helpful information for guests visiting Rameswaram and staying at **Hotel Harriet**.

**RESPONSE GUIDELINES:**
1. **Travel Guide:** If the user asks about travel (Train \U0001f686, Bus \U0001f68c, Flight \u2708\ufe0f), use your INTERNAL WORLD KNOWLEDGE to provide a guide. Do NOT look for travel schedules in the provided context as we do not use RAG for transport.
2. **Hotel Harriet Information:** If the user asks about the hotel, amenities, or room stay details, use ONLY the information provided in the Context below.
3. **Unified Answer:** Always combine both if asked, providing travel info from your knowledge and hotel info from the context.
4. **Structured Format:** Use clear headings, bullet points, and emojis.

**Example Structure:**
\U0001f3e8 **Travel Guide: [Origin] to Rameswaram**

\U0001f686 **Train Options:**
[Based on AI internal knowledge]

\U0001f68c **Bus Services:**
[Based on AI internal knowledge]

\u2708\ufe0f **Flight Connections:**
[Nearest: Madurai IXM]

---
\U0001f3e8 **Stay at Hotel Harriet:**
[ONLY FROM CONTEXT PROVIDED BELOW]

\U0001f4a1 **Expert Tip:**
[A helpful recommendation based on your travel knowledge]

Context:
{context}

Question: {question}

Answer:""")
            
            chain = prompt_template | self.llm
            for attempt in range(max_retries):
                try:
                    response = chain.invoke({"context": context_text, "question": final_query})
                    return response.content
                except Exception as e:
                    error_str = str(e)
                    if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < max_retries - 1:
                        logging.warning(f"Generation rate limit hit. Retrying in {retry_delay}s... ({attempt+1}/{max_retries})")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logging.error(f"Error gathering hotel answer: {e}")
                        return "I encountered an error trying to answer your question. Please try again in a moment."
            return "Service temporarily busy. Please try again."

        else:
            # ===== PATH B: GENERIC QUESTION — Direct AI (no RAG context) =====
            logging.info(f"[AI PATH] Answering generic question directly: {final_query}")
            generic_prompt = ChatPromptTemplate.from_template("""You are 'Harriet Guide Bot', an AI assistant exclusively for Hotel Harriet and its surrounding areas in Rameswaram.

You may ONLY answer questions related to:
1. Hotel Harriet — facilities, policies, general hotel queries.
2. Rameswaram — temples, tourist spots, local culture, weather, food, shopping.
3. Travel — how to reach Rameswaram, trains, buses, flights, nearby cities.
4. Local tips — restaurants, beaches, best times to visit, safety tips.

Rules:
- If the question is related to the hotel or Rameswaram area, answer clearly with bullet points and emojis.
- If the question is completely UNRELATED (e.g., coding, politics, science, math, sports, entertainment, personal advice), politely decline by saying:
  "I'm your Hotel Harriet assistant and can only help with hotel services, Rameswaram travel, and local area information. 😊 Feel free to ask me anything about your stay or visit!"
- Do NOT answer generic or off-topic questions under any circumstances.

Question: {question}

Answer:""")
            
            chain = generic_prompt | self.llm
            for attempt in range(max_retries):
                try:
                    response = chain.invoke({"question": final_query})
                    return response.content
                except Exception as e:
                    error_str = str(e)
                    if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < max_retries - 1:
                        logging.warning(f"Generic AI rate limit hit. Retrying in {retry_delay}s... ({attempt+1}/{max_retries})")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logging.error(f"Error generating generic answer: {e}")
                        return "I encountered an error trying to answer your question. Please try again in a moment."
            return "Service temporarily busy. Please try again."
