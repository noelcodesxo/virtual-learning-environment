import re
from collections import defaultdict

import ebooklib
from bs4 import BeautifulSoup, NavigableString
from ebooklib import epub

class Chunker():
    CHUNK_SIZE = 250
    CHUNK_OVERLAP = 20
    BLOCK_TAGS = {'p', 'div', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                  'pre', 'td', 'th', 'tr', 'dd', 'dt'}
    PARAGRAPH_SPLIT_RE = re.compile(r'\n\s*\n')
    SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')

    def __init__(self):
        self.chunks = []

    def flatten_toc(self, toc, depth=0):
        """Flatten book.toc into (filename, anchor_or_None, title, depth) tuples,
        in document order. depth 0 = chapter, depth >= 1 = section/subsection."""
        flat = []
        for node in toc:
            if isinstance(node, tuple):
                section, children = node
                flat.append((*self.split_href(section.href), section.title, depth))
                flat.extend(self.flatten_toc(children, depth + 1))
            else:
                flat.append((*self.split_href(node.href), node.title, depth))
        return flat


    def split_href(self, href):
        filename, _, anchor = href.partition('#')
        return filename, anchor or None


    def build_landmark_map(self, book):
        """filename -> {anchor_or_None: (title, depth)}"""
        by_file = defaultdict(dict)
        for filename, anchor, title, depth in self.flatten_toc(book.toc):
            by_file[filename][anchor] = (title, depth)
        return by_file


    def walk(self, tag, landmarks, context, out):
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

        if tag.name in self.BLOCK_TAGS:
            context['block'] = id(tag)

        for child in tag.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    current_block = context.get('block')
                    if 'last_block' in context and current_block != context['last_block']:
                        text = '\n\n' + text
                    context['last_block'] = current_block
                    out.append((text, context['chapter'], context['section']))
            elif child.name is not None:
                self.walk(child, landmarks, context, out)


    def merge_blocks(self, leaves):
        """Merge consecutive leaf texts that share the same (chapter, section)
        into single blocks, so chunking doesn't operate on tiny fragments."""
        blocks = []
        for text, chapter, section in leaves:
            if blocks and blocks[-1][1] == chapter and blocks[-1][2] == section:
                sep = '' if text.startswith('\n\n') else ' '
                blocks[-1] = (blocks[-1][0] + sep + text, chapter, section)
            else:
                blocks.append((text, chapter, section))
        return blocks


    def context_rewrite(self, book):
        """Extract (text, chapter, section) blocks for every document in the
        book, using the epub's own TOC as the source of chapter/section titles.
        Falls back to chapter=section=None when a book has no usable TOC."""
        landmark_map = self.build_landmark_map(book)
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
            self.walk(body, landmarks, context, leaves)
            blocks.extend(self.merge_blocks(leaves))

        return blocks


    def chunker_processer(self, text: str, chapter: str | None, section: str | None):
        text = text.strip()
        if not text:
            return

        if len(text) <= self.CHUNK_SIZE:
            self.chunks.append({'text': text, 'chapter': chapter, 'section': section})
            return

        paragraphs = [p.strip() for p in self.PARAGRAPH_SPLIT_RE.split(text) if p.strip()]
        if len(paragraphs) > 1:
            for paragraph in paragraphs:
                self.chunker_processer(paragraph, chapter, section)
            return

        sentences = [s.strip() for s in self.SENTENCE_SPLIT_RE.split(text) if s.strip()]
        if len(sentences) > 1:
            for sentence in sentences:
                self.chunker_processer(sentence, chapter, section)
            return

        for piece in self.split_words_with_overlap(text):
            self.chunks.append({'text': piece, 'chapter': chapter, 'section': section})


    def split_words_with_overlap(self, text: str) -> list[str]:
        """Pack whole words into <= CHUNK_SIZE pieces, never splitting a word.
        Each piece after the first repeats ~CHUNK_OVERLAP trailing chars
        (rounded up to whole words) from the previous piece."""
        words = text.split()
        pieces = []
        start = 0
        while start < len(words):
            end = start
            length = 0
            while end < len(words):
                extra = len(words[end]) if end == start else len(words[end]) + 1
                if length + extra > self.CHUNK_SIZE and end > start:
                    break
                length += extra
                end += 1
            pieces.append(' '.join(words[start:end]))

            if end >= len(words):
                break

            overlap_start = end
            overlap_len = 0
            while overlap_start > start and overlap_len < self.CHUNK_OVERLAP:
                overlap_start -= 1
                overlap_len += len(words[overlap_start]) + 1
            start = overlap_start if overlap_start > start else end
        return pieces

    def book_title(self, book: epub.EpubBook) -> str | None:
        metadata = book.get_metadata('DC', 'title')
        return metadata[0][0] if metadata else None

    def process_book(self, book: epub.EpubBook) -> list[dict]:
        self.chunks = []
        for text, chapter, section in self.context_rewrite(book):
            self.chunker_processer(text, chapter, section)

        title = self.book_title(book)
        for chunk in self.chunks:
            chunk['book'] = title

        return self.chunks

    def process_books(self, books: list[epub.EpubBook]) -> list[list[dict]]:
        return [self.process_book(book) for book in books]