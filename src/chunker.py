from collections import defaultdict

import ebooklib
from bs4 import BeautifulSoup, NavigableString
from ebooklib import epub

book = epub.read_epub('/home/noelcodes/dev/projects/learning_env_experiments/src/resources/aiengineering.epub')
chunks = []
CHUNK_SIZE = 250


def flatten_toc(toc, depth=0):
    """Flatten book.toc into (filename, anchor_or_None, title, depth) tuples,
    in document order. depth 0 = chapter, depth >= 1 = section/subsection."""
    flat = []
    for node in toc:
        if isinstance(node, tuple):
            section, children = node
            flat.append((*split_href(section.href), section.title, depth))
            flat.extend(flatten_toc(children, depth + 1))
        else:
            flat.append((*split_href(node.href), node.title, depth))
    return flat


def split_href(href):
    filename, _, anchor = href.partition('#')
    return filename, anchor or None


def build_landmark_map(book):
    """filename -> {anchor_or_None: (title, depth)}"""
    by_file = defaultdict(dict)
    for filename, anchor, title, depth in flatten_toc(book.toc):
        by_file[filename][anchor] = (title, depth)
    return by_file


def walk(tag, landmarks, context, out):
    """Depth-first walk in document order. Whenever a tag's id matches a
    landmark for this file, update the current chapter/section context.
    Every leaf text node is tagged with whatever context is active."""
    tag_id = tag.get('id')
    if tag_id in landmarks:
        title, depth = landmarks[tag_id]
        if depth == 0:
            context['chapter'] = title
            context['section'] = None
        elif depth == 1:
            context['section'] = title
        # depth >= 2: subsections inherit whatever section they're nested in

    for child in tag.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                out.append((text, context['chapter'], context['section']))
        elif child.name is not None:
            walk(child, landmarks, context, out)


def merge_blocks(leaves):
    """Merge consecutive leaf texts that share the same (chapter, section)
    into single blocks, so chunking doesn't operate on tiny fragments."""
    blocks = []
    for text, chapter, section in leaves:
        if blocks and blocks[-1][1] == chapter and blocks[-1][2] == section:
            blocks[-1] = (blocks[-1][0] + ' ' + text, chapter, section)
        else:
            blocks.append((text, chapter, section))
    return blocks


def context_rewrite(book):
    """Extract (text, chapter, section) blocks for every document in the
    book, using the epub's own TOC as the source of chapter/section titles.
    Falls back to chapter=section=None when a book has no usable TOC."""
    landmark_map = build_landmark_map(book)
    blocks = []

    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        filename = item.get_name()
        landmarks = landmark_map.get(filename, {})
        context = {'chapter': None, 'section': None}

        # A fragment-less TOC entry (href="ch01.html") means the whole file
        # starts under that chapter/section.
        if None in landmarks:
            title, depth = landmarks[None]
            if depth == 0:
                context['chapter'] = title
            elif depth == 1:
                context['section'] = title

        soup = BeautifulSoup(item.get_content(), 'html.parser')
        body = soup.find('body') or soup

        leaves = []
        walk(body, landmarks, context, leaves)
        blocks.extend(merge_blocks(leaves))

    return blocks


def chunker():
    for text, chapter, section in context_rewrite(book):
        chunker_processer(text, chapter, section)
    print(chunks)
    print(len(chunks))
    

def chunker_processer(text: str, chapter: str | None, section: str | None):
    if len(text) <= CHUNK_SIZE:
        if text.strip():
            chunks.append({'text': text, 'chapter': chapter, 'section': section})
        return
    else:
        x = 0
        while x < len(text):
            chunker_processer(text[x:x + CHUNK_SIZE], chapter, section)
            x += CHUNK_SIZE


chunker()
