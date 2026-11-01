class IdFactory:
    def __init__(self): self.counts={}
    def next(self, kind, prefix, width=6):
        n=self.counts.get(kind,0)+1; self.counts[kind]=n
        return f"{prefix}{n:0{width}d}"
    def year(self, kind, prefix, year=2026, width=6):
        n=self.counts.get(kind,0)+1; self.counts[kind]=n
        return f"{prefix}{year}-{n:0{width}d}"
