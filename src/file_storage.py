import os
import json
import uuid

class FileStorage:
    def __init__(self, root_dir):
        """
        Storage engine that saves articles as individual files.
        Structure:
        root_dir/
            articles/
                {safe_title}/
                    content.md
                    abstract.md
                    toc.json
                    sidecar.json
        """
        self.root_dir = root_dir
        os.makedirs(os.path.join(root_dir, "articles"), exist_ok=True)

    def save_article(self, processed_data):
        """
        Saves the shredded article to disk.
        processed_data: Dict returned by WikiShredder.process()
        """
        title = processed_data['title']
        # Create a safe directory name from title (or use a hash/ID if available)
        safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        if not safe_title:
             safe_title = "untitled_" + uuid.uuid4().hex[:8]

        article_dir = os.path.join(self.root_dir, "articles", safe_title)
        os.makedirs(article_dir, exist_ok=True)

        # 1. Full Text
        with open(os.path.join(article_dir, "content.md"), "w", encoding="utf-8") as f:
            f.write(processed_data['content'])

        # 2. Abstract
        with open(os.path.join(article_dir, "abstract.md"), "w", encoding="utf-8") as f:
            f.write(processed_data['abstract'])

        # 3. Table of Contents
        with open(os.path.join(article_dir, "toc.json"), "w", encoding="utf-8") as f:
            json.dump(processed_data['toc'], f, indent=2)

        # 4. Sidecar (Optional but recommended)
        with open(os.path.join(article_dir, "sidecar.json"), "w", encoding="utf-8") as f:
            json.dump(processed_data['sidecar'], f, indent=2)
            
        return article_dir
