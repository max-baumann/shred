This is like sooo work in progress and yes significant parts where written by Claude Sonnet 4.5.

# S.H.R.E.D.
**Semantic Hybrid Retrieval & Extraction Database**

> _Because your AI agent does **not** need to DDoS every small wiki on the internet to feel smart._


## What Is This?

**S.H.R.E.D.** is a **local, space-efficient RAG architecture** that takes **compressed Wikipedia archives**, parses them into **structured Markdown** and **semantic tokens**, and lets you run **high-speed expert-system queries** without hauling around petabytes of junk or harassing volunteer-run websites. Special attention was given to extracting structured information like tables, formulars and infoboxes. It's all about making a wiki more machine readable.

In short:
-  **Offline**
-  **Semantic**
-  **Fast**


## Why Does This Exist?

Because somewhere along the line, people decided that the correct way to build AI systems was:

1. Write a half-baked parser  
2. Point it at a random wiki  
3. Ignore robots.txt  
4. Hammer the server with parallel requests  
5. Call it “research”

Wikipedia already publishes **compressed dumps**.  
They are **meant** to be used.  
Use them. Like an adult.


## What It Actually Does

S.H.R.E.D. takes:
-  Compressed Wikipedia archives  
-  Parses them into clean, navigable **Markdown**
-  Extracts **semantic tokens** for retrieval
- ️ Stores everything in a **space-efficient local database**
-  Enables **expert-level RAG queries** without giant vector stores

All while:
- Respecting infrastructure
- Avoiding live scraping
- Not being That Guy™
