# Literature Evidence Skill

This skill provides optional PubMed retrieval through Biopython Entrez. It is
used to gather source-backed biomedical context for reports, manuscripts, and
method discussions.

Required configuration:
- `NCBI_EMAIL` or `ENTREZ_EMAIL` in `.env` or the runtime environment.

Optional configuration:
- `NCBI_API_KEY` for higher NCBI request limits.

Rules:
- Use literature search only when the user asks for evidence, references, or
  source-backed background.
- Report PubMed IDs and source metadata.
- Do not treat retrieved literature as direct validation of the current local
  analysis unless the relevant benchmark or dataset has actually been run.
