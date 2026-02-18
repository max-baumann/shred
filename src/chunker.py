import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict

# Constants from Spec
MIN_TOKENS = 80
TARGET_TOKENS = 220
MAX_TOKENS = 300
SENTENCE_OVERLAP = 1 

@dataclass
class Section:
    title: str
    level: int
    path: List[str]
    content: List[str] = field(default_factory=list) # List of paragraph strings
    subsections: List['Section'] = field(default_factory=list)

@dataclass
class Chunk:
    chunk_id: str
    article_id: str
    text: str
    token_count: int
    chunk_type: str # paragraph | merged | split
    section_path: List[str]
    paragraph_index: int
    subchunk_index: Optional[int]

class UniversalChunker:
    def __init__(self, tokenizer_func=None):
        """
        :param tokenizer_func: Function that takes str and returns int (token count).
                               Defaults to simple whitespace splitting if None.
        """
        self.tokenizer = tokenizer_func if tokenizer_func else self._simple_tokenize

    def _simple_tokenize(self, text):
        return len(text.split())

    def _split_sentences(self, text):
        """
        Simple sentence splitter. For production, use nltk or spacy.
        """
        # Heuristic: split on ". " "! " "? " but keep the punctuation.
        # This is a basic implementation.
        pattern = r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def chunk_article(self, article_id: str, markdown_content: str) -> List[Chunk]:
        """
        Main entry point. Parses Markdown and produces Chunks.
        """
        # 1. Parse Markdown into Section Hierarchy
        root_section = self._parse_markdown_structure(markdown_content)
        
        # 2. Traverse and Chunk
        return self._recursive_chunk_process(article_id, root_section)

    def _recursive_chunk_process(self, article_id: str, section: Section) -> List[Chunk]:
        chunks = []
        # Process current section content
        chunks.extend(self._process_section_content(article_id, section))
        
        # Process subsections
        for subsection in section.subsections:
            chunks.extend(self._recursive_chunk_process(article_id, subsection))
            
        return chunks

    def _parse_markdown_structure(self, text: str) -> Section:
        """
        Parses ATX-style markdown (# Header) into a Section tree.
        """
        lines = text.split('\n')
        root = Section(title="Root", level=0, path=["Root"])
        
        # Stack of (Section, level)
        section_stack = [root] 
        current_section = root
        
        current_paragraph_lines = []

        def flush_paragraph():
            nonlocal current_paragraph_lines
            if current_paragraph_lines:
                p_text = " ".join(current_paragraph_lines).strip()
                if p_text:
                    current_section.content.append(p_text)
                current_paragraph_lines = []

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                # Blank lines might signify paragraph breaks
                flush_paragraph()
                continue
            
            # Check for Header
            header_match = re.match(r'^(#+)\s+(.*)', line_stripped)
            if header_match:
                flush_paragraph() # Finish prev section text
                
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                
                # Pop stack until we find the parent (level < new_level)
                while len(section_stack) > 1 and section_stack[-1].level >= level:
                    section_stack.pop()
                
                parent = section_stack[-1]
                
                # Path includes parent path + title (skip Root in path if desired, but spec says "section_path")
                # Usually we want ["History", "Early Years"]
                # Root path is ["Root"]. Sub is ["Root", "History"]?
                # Let's strip "Root" for cleaner paths if parent is root
                base_path = parent.path
                if len(base_path) == 1 and base_path[0] == "Root":
                     base_path = []
                
                path = base_path + [title]
                
                new_section = Section(title=title, level=level, path=path)
                parent.subsections.append(new_section)
                
                # Update State
                current_section = new_section
                section_stack.append(new_section)
            else:
                # Accumulate text
                current_paragraph_lines.append(line_stripped)
        
        flush_paragraph() # Final flush
        return root

    def _process_section_content(self, article_id: str, section: Section) -> List[Chunk]:
        """
        Applies logic from Spec (Rule 2 + 3)
        """
        chunks = []
        
        # Buffer stores (text, original_index)
        # We need a small class or tuple
        buffer_text = None
        buffer_idx = -1

        for i, paragraph_text in enumerate(section.content):
            tokens = self.tokenizer(paragraph_text)

            # Rule 2 Case B: Small paragraph -> Add to Buffer
            if tokens < MIN_TOKENS:
                if buffer_text is None:
                    # Start Buffer
                    buffer_text = paragraph_text
                    buffer_idx = i
                else:
                    # Try Merge
                    merged_candidate = buffer_text + "\n\n" + paragraph_text
                    merged_tokens = self.tokenizer(merged_candidate)
                    
                    if merged_tokens <= MAX_TOKENS:
                        buffer_text = merged_candidate
                        # buffer_idx remains start idx
                    else:
                        # Cannot merge, emit buffer
                        self._emit_chunk(chunks, article_id, section.path, buffer_text, 
                                         self.tokenizer(buffer_text), "merged", buffer_idx)
                        # Start new buffer with current
                        buffer_text = paragraph_text
                        buffer_idx = i
                continue

            # If we are here, current paragraph is >= MIN_TOKENS or we broke the buffer chain
            
            # 1. Flush Buffer if exists (because we hit a big paragraph that breaks the small-chain)
            if buffer_text is not None:
                # Can we merge the big paragraph INTO the buffer?
                # Spec: "Attempt forward merge... If merge exceeds MAX_TOKENS, do not merge."
                # We already know current is >= MIN_TOKENS. 
                # If current is HUGE, we definitely flush buffer.
                # If current is medium, we might merge?
                # Logic above: "Case B: ... < MIN_TOKENS". This block is for >= MIN case.
                # So we simply flush buffer as independent chunk.
                
                self._emit_chunk(chunks, article_id, section.path, buffer_text,
                                 self.tokenizer(buffer_text), "merged", buffer_idx)
                buffer_text = None
                buffer_idx = -1
            
            # 2. Process Current
            if tokens <= MAX_TOKENS:
                 # Case A: Emit single
                 self._emit_chunk(chunks, article_id, section.path, paragraph_text, tokens, "paragraph", i)
            else:
                 # Case C: Split
                 self._split_long_paragraph(chunks, article_id, section, paragraph_text, i)
        
        # Final Flush
        if buffer_text is not None:
             self._emit_chunk(chunks, article_id, section.path, buffer_text,
                              self.tokenizer(buffer_text), "merged", buffer_idx)
        
        return chunks

    def _split_long_paragraph(self, chunks_list, article_id, section, text, paragraph_index):
        sentences = self._split_sentences(text)
        
        # Check empty
        if not sentences:
            return

        i = 0
        sub_idx = 0
        
        while i < len(sentences):
            window = []
            token_sum = 0
            
            # Build Window: Accumulate until TARGET_TOKENS
            # While loop to build ONE window
            while i < len(sentences):
                s_text = sentences[i]
                s_len = self.tokenizer(s_text)
                
                # Check for overflow BEFORE adding if we already have content?
                # Spec says "Accumulate ... until TARGET_TOKENS is reached".
                # Usually means allow slightly over TARGET to complete the sent, 
                # OR stop before overflowing MAX?
                # Spec only lists TARGET. Let's aim for >= TARGET.
                
                window.append(s_text)
                token_sum += s_len
                i += 1
                
                if token_sum >= TARGET_TOKENS:
                    break
            
            chunk_text = " ".join(window)
            self._emit_chunk(chunks_list, article_id, section.path, chunk_text, token_sum, "split", paragraph_index, sub_idx)
            sub_idx += 1
            
            # Advance Window logic:
            # "Advance window start by: window_start += window_size - SENTENCE_OVERLAP"
            # Current 'i' is the END of the window (exclusive).
            # Window size (in sentences) = len(window)
            # New Start should imply overlap.
            # So if we consumed 5 sentences, and overlap is 1, we want 
            # the next window to start at index of (last sentence).
            # Current `i` is 5. We want to restart at 4.
            # i = i - overlap.
            
            overlap_count = SENTENCE_OVERLAP
            # Safety: Don't overlap infinitely if window is tiny
            if overlap_count >= len(window):
                overlap_count = max(0, len(window) - 1)
            
            # We backtrack i
            if i < len(sentences): # Only backtrack if we have more to process
                i -= overlap_count

    def _emit_chunk(self, chunks_list, article_id, section_path, text, tokens, c_type, p_idx, sub_idx=None):
        sub_str = str(sub_idx) if sub_idx is not None else ""
        path_str = "/".join(section_path)
        
        # Spec 1.6 Chunk Identity
        # chunk_id = hash(article_id + section_path + paragraph_index + subchunk_index)
        raw_id = f"{article_id}|{path_str}|{p_idx}|{sub_str}"
        chunk_id = hashlib.md5(raw_id.encode('utf-8')).hexdigest()[:16] # 16 chars enough?
        
        chunks_list.append(Chunk(
            chunk_id=chunk_id,
            article_id=article_id,
            text=text,
            token_count=tokens,
            chunk_type=c_type,
            section_path=section_path,
            paragraph_index=p_idx,
            subchunk_index=sub_idx
        ))

    # Wiring for loop (Overwriting the simple one with fixed one)
    _process_section_content = _process_section_content_fixed
