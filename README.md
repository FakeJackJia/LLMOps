# LLMOps Platform Backend (Dify-like)

A lightweight, Dify-inspired platform for building and deploying LLM-powered agents.  
It provides **visual orchestration, single-agent workflows, knowledge base retrieval, plugin integration, and multi-LLM support** with a modular backend design.  

---

## 🚀 Features

- **Visual Workflow Orchestration**  
  Build and manage agent workflows using LangGraph, with streaming SSE outputs.  

- **Single-Agent Support**  
  Create function-calling agents that can reason, call tools, and collaborate in workflows.  

- **Knowledge Base & RAG**  
  - Unstructured document parsing (PDF, Word, PPT, CSV, Markdown, etc.)  
  - Recursive text splitting & token counting  
  - Embedding & vector storage (Weaviate, FAISS)  
  - Hybrid retrieval (semantic + keyword search with jieba)  
  - Celery-based async indexing  

- **Plugin System**  
  - Built-in tools: DuckDuckGo, Wikipedia, Serper, Gaode Weather, Time, DALL·E  
  - Custom tools via OpenAPI schema → auto Pydantic parameter model generation  

- **Multi-LLM Integration**  
  Unified interface for OpenAI, Tongyi, Ollama, and more, with token & cost tracking.  

- **Deployment & Security**  
  - JWT & GitHub OAuth authentication, API key management  
  - Draft/Publish app versioning & rollback  

---

## 🛠 Tech Stack

- **Backend:** Python, Flask, Injector  
- **LLM Frameworks:** LangChain, LangGraph  
- **Data & Retrieval:** Weaviate, FAISS, Jieba, Unstructured  
- **Async & Streaming:** Celery, Redis, SSE  
- **Database:** SQLAlchemy (PostgreSQL) 
