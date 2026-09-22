import string


class PreProcessor():
    STRIP_CHARS = string.punctuation + '‘’“”–—―'

    STOP_WORDS = {
        'a', 'an', 'and', 'the', 'or', 'of', 'to', 'in', 'for', 'on', 'with',  
        'at', 'by', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him',  
        'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their', 'this',  
        'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being',  
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'shall', 'should',  
        'may', 'might', 'must', 'can', 'could', 'as', 'but', 'if', 'or', 'because',  
        'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between',  
        'into', 'through', 'during', 'before', 'after', 'above', 'below', 'from', 'up',  
        'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then',  
        'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both',  
        'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',  
        'only', 'own', 'same', 'so', 'than', 'too', 'very'  
    }

    def process(self, chunk: str) -> str:
        words = (w.lower().strip(self.STRIP_CHARS) for w in chunk.split())
        return ' '.join(word for word in words if word and word not in self.STOP_WORDS)