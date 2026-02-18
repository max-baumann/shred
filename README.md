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

## In more Detail
The system transforms raw Wikipedia HTML into structured, machine-readable data through a three-stage process:


### 1. The Core Pipeline
The system transforms raw Wikipedia HTML into structured, machine-readable data through a three-stage process:

#### Stage 1: Shredding (`WikiShredder`)

    *   **Input:** Raw HTML.
    *   **Extraction:** Separates "heavy" semi-structured data (Infoboxes, Tables, Formulas) into a **Sidecar JSON** dictionary.
    *   **Replacement:** Injects robust tokens (e.g., `**[<<TABLE: TBL_123 | GDP Data>>]**`) into the text where extraction occurred.
    *   **Normalization:** Rewrites image tags to the `zim://` protocol (Zero-Extraction) and converts the remaining flow text into clean **Markdown**.
    
#### Stage 2: Chunking (`UniversalChunker`)

    *   **Input:** Cleaned Markdown.
    *   **Logic:** Parses the Markdown header structure to build a section tree. Applies semantic grouping rules (merging small paragraphs, splitting long ones via sliding window) to create optimal contexts for vector search.
    *   **Output:** Hierarchical chunks with stable, deterministic IDs.
    
#### Stage 3: Storage (`WikiStorage`)
    *   **Backend:** PostgreSQL + `pgvector`.
    *   **Schema:** Stores the full Article (Text + Sidecar), individual Chunks, and their computed Vector Embeddings in a relational structure.

### 2. The "Zero-Extraction" Media Layer
*   **Storage:** Images are **not** extracted to individual files. They remain compressed inside the source ZIM file.
*   **Access:** The text references images via `zim://I/filename.jpg`.
*   **Serving:** A lightweight **FastAPI Media Server** uses `libzim` to read binary blobs directly from the archive on demand, preventing file system exhaustion.

### 3. Data Model
*   **Main Text:** Lightweight Markdown optimized for LLM reading.
*   **Sidecar:** Structured JSON holding metadata, CSV representations of tables, and raw infobox HTML for specialized parsing.
*   **Vector Index:** A semantic search layer built on the semantically chunked text.
