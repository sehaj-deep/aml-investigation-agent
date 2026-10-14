### Sprint 3: RAG over AML guidance
**Build:** Corpus ingestion and chunking with jurisdiction tags. pgvector plus full-text hybrid search with local embeddings. `retrieve_guidance` MCP tool. Citation validation. Hand-labeled pattern-to-guidance set.
**Done when:** Narratives cite guidance passages, citations validate against the index, and recall@k is reported.
**Verify:**
- Spot-check about 20 chunks against the source PDFs, especially tables and headers.
- Compare keyword-only, vector-only and hybrid retrieval on the labeled set. Hybrid should be at least as good as either; if not, investigate.
- Alter a quoted span and confirm it is caught.
- Run a Canadian case and a US case and confirm no jurisdiction leakage.
- Query something unrelated and confirm "no guidance found".
**Resume bullet template:**
> Implemented hybrid-search RAG over public AML typology guidance with jurisdiction filtering, exposed through an MCP tool, with citation validation; retrieval recall@[k] of [X] on a hand-labeled set of [N] queries.
