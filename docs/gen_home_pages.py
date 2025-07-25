"""Generate the home pages."""
import os

import mkdocs_gen_files


# Read README.md from project root
readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")

# Read the content of README.md
with open(readme_path, encoding='utf-8') as f:
    content = f.read()

# Write the content to index.md in the docs directory
with mkdocs_gen_files.open("index.md", "w") as f:
    f.write(content)
