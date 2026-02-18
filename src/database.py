import json
try:
    import psycopg
    from pgvector.psycopg import register_vector
    from sentence_transformers import SentenceTransformer
except ImportError:
    psycopg = None
    register_vector = None
    SentenceTransformer = None

from .chunker import UniversalChunker

class WikiStorage:
    def __init__(self, db_conn_string, model_name='all-MiniLM-L6-v2', batch_size=100):
        """
        Initializes the storage engine.
        """
        self.conn_string = db_conn_string
        self.batch_size = batch_size
        
        # Load the Embedding Model
        if SentenceTransformer:
            print(f"Loading embedding model: {model_name}...")
            self.model = SentenceTransformer(model_name)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            # If using HF tokenizer, wrap it for Chunker
            self.chunker = UniversalChunker(self._hf_tokenize)
        else:
            print("Warning: SentenceTransformer not installed. Embeddings disabled.")
            self.model = None
            self.embedding_dim = 384 
            # Default Chunker uses whitespace tokenization
            self.chunker = UniversalChunker()

        self._article_buffer = []
        self._asset_buffer = []
        self._chunk_buffer = []

    def _hf_tokenize(self, text):
        return len(self.model.tokenizer.encode(text))

    def setup_schema(self):

    def setup_schema(self):
        """
        Idempotent schema setup.
        """
        if not psycopg:
            print("Psycopg not installed, skipping schema setup.")
            return

        with psycopg.connect(self.conn_string, autocommit=True) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            register_vector(conn)

            # 1. Articles Table
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS articles (
                    id SERIAL PRIMARY KEY,
                    zim_path TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    markdown_content TEXT,
                    abstract TEXT,
                    toc JSONB,
                    embedding vector({self.embedding_dim})
                );
            """)

            # 2. Assets (Sidecar) Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    article_zim_path TEXT REFERENCES articles(zim_path) ON DELETE CASCADE,
                    type TEXT NOT NULL, 
                    summary TEXT,
                    data JSONB
                );
            """)

            # 3. Chunks Table
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    article_zim_path TEXT REFERENCES articles(zim_path) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    token_count INT,
                    chunk_type TEXT,
                    section_path TEXT[],
                    paragraph_index INT,
                    embedding vector({self.embedding_dim})
                );
            """)

            # 4. Indexes
            print("Creating indexes...")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_embedding 
                ON articles USING hnsw (embedding vector_cosine_ops);
            """)
            conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
                ON chunks USING hnsw (embedding vector_cosine_ops);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_assets_data 
                ON assets USING GIN (data);
            """)
            
            print("Schema setup complete.")

    def add_article(self, zim_path, processed_data):
        """
        Adds an article to the processing buffer.
        processed_data is the dict returned by WikiShredder.process()
        """
        title = processed_data['title']
        content = processed_data['content']
        abstract = processed_data['abstract']
        toc = processed_data['toc']
        sidecar = processed_data['sidecar']

        # Generate Embedding
        vector = None
        if self.model and abstract:
            vector = self.model.encode(abstract).tolist()

        # Add to Buffer
        self._article_buffer.append((
            zim_path, 
            title, 
            content, 
            abstract, 
            json.dumps(toc),
            vector
        ))

        # Add Assets to Buffer
        # Flatten sidecar for storage
        for asset_type, assets in sidecar.items():
            for uid, data in assets.items():
                summary = data.get('summary', '')
                if not summary and asset_type == 'images':
                    summary = data.get('alt', '')
                
                self._asset_buffer.append((
                    uid,
                    zim_path,
                    asset_type,
                    summary,
                    json.dumps(data)
                ))

        # --- Chunking Pipeline ---
        chunks = self.chunker.chunk_article(zim_path, content)
        
        # Batch Embed Chunks (if model exists)
        if self.model and chunks:
            raw_texts = [c.text for c in chunks]
            # Batch encode
            embeddings = self.model.encode(raw_texts).tolist()
        else:
            embeddings = [None] * len(chunks)

        for i, chunk in enumerate(chunks):
            self._chunk_buffer.append((
                chunk.chunk_id,
                zim_path,
                chunk.text,
                chunk.token_count,
                chunk.chunk_type,
                chunk.section_path, # List[str] maps to TEXT[] in PG
                chunk.paragraph_index,
                embeddings[i]
            ))

        if len(self._article_buffer) >= self.batch_size:
            self._flush()

    def _flush(self):
        if not psycopg:
            print("Mock Flush: DB not connected.")
            self._article_buffer = []
            self._asset_buffer = []
            self._chunk_buffer = []
            return

        with psycopg.connect(self.conn_string, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Bulk Insert Articles
                # Note: This is simplified. use copy() or execute_values() for real bulk speed.
                for row in self._article_buffer:
                    cur.execute("""
                        INSERT INTO articles (zim_path, title, markdown_content, abstract, toc, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (zim_path) DO NOTHING
                    """, row)

                # Bulk Insert Assets
                for row in self._asset_buffer:
                    cur.execute("""
                        INSERT INTO assets (asset_id, article_zim_path, type, summary, data)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (asset_id) DO NOTHING
                    """, row)

                # Bulk Insert Chunks
                # section_path (list) works with psycopg3 binary adaptation to ARRAY
                for row in self._chunk_buffer:
                    cur.execute("""
                        INSERT INTO chunks (chunk_id, article_zim_path, text, token_count, chunk_type, section_path, paragraph_index, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (chunk_id) DO NOTHING
                    """, row)
        
        self._article_buffer = []
        self._asset_buffer = []
        self._chunk_buffer = []

    def close(self):
        if self._article_buffer:
            self._flush()
