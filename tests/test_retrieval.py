import math

from assetscope.models import Citation, EvidenceItem, SourceType
from assetscope.retrieval.embeddings import HashingEmbedder
from assetscope.retrieval.hybrid import HybridRetriever
from assetscope.retrieval.vector_store import InMemoryStore


def test_hashing_embedder_deterministic_and_normalized():
    emb = HashingEmbedder(32)
    a = emb.encode_one("tirzepatide dual GIP GLP-1 agonist obesity")
    b = emb.encode_one("tirzepatide dual GIP GLP-1 agonist obesity")
    assert len(a) == 32
    assert a == b  # deterministic
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-6)
    c = emb.encode_one("completely different sentence about kras")
    assert a != c


def _item(cid, text, st=SourceType.CLINICAL_TRIALS):
    return EvidenceItem(
        citation=Citation(id=cid, source_type=st, source_id=cid, url=f"u/{cid}", title=cid),
        content=text,
    )


def test_hybrid_retriever_ingest_and_search():
    retr = HybridRetriever(store=InMemoryStore(), embedder=HashingEmbedder(64))
    n = retr.ingest(
        [
            _item("NCT1", "Tirzepatide is a dual GIP and GLP-1 receptor agonist for obesity."),
            _item("NCT2", "Sotorasib is a covalent KRAS G12C inhibitor for lung cancer."),
            _item("PMID3", "Ibrutinib is a covalent BTK inhibitor for chronic lymphocytic leukemia.", SourceType.PUBMED),
        ]
    )
    assert n == 3
    hits = retr.search("KRAS G12C inhibitor lung cancer", k=3)
    assert hits, "expected at least one hit"
    # the sotorasib doc should rank top via keyword + vector fusion
    assert hits[0].citation.id == "NCT2"
    assert hits[0].rrf_score > 0


def test_rrf_merge_dedupes_across_modalities():
    from assetscope.retrieval.vector_store import RetrievedChunk

    cit = Citation(id="NCT1", source_type=SourceType.CLINICAL_TRIALS, source_id="NCT1")
    v = [RetrievedChunk(citation=cit, content="same text here", score=0.9, modality="vector")]
    k = [RetrievedChunk(citation=cit, content="same text here", score=2.0, modality="keyword")]
    merged = HybridRetriever._rrf_merge(v, k, 5)
    assert len(merged) == 1
    assert merged[0].vector_score == 0.9 and merged[0].keyword_score == 2.0
