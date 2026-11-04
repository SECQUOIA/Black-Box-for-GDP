# Journal submission materials

The scientific article has one source, [`../main.tex`](../main.tex).
[`../arxiv.tex`](../arxiv.tex) includes the shared supplement in the same PDF.
[`../cace.tex`](../cace.tex) produces an article-only PDF and imports the
standalone supplement's labels, so references to supplementary sections,
tables, and figures retain their numbers and link to `supplementary.pdf`.
The manuscript uses the existing `article` class and author–year references;
the CACE entry point does not claim a journal-specific typeset layout.

## Author-confirmed statements

- All authors approved the journal submission; the manuscript is not under
  consideration at another journal. No arXiv preprint has been posted yet.
- There are no competing interests to declare.
- The Davidson School of Chemical Engineering at Purdue University provided
  the only funding and had no role in the study or submission decision.
- Albert Joon Lee contributed implementation, investigation, formal analysis,
  validation, visualization, and drafting. Woosik Kim contributed the
  factorization-machine method with simulated annealing, validation, and
  visualization.
  David E. Bernal Neira contributed across the research, software, analysis,
  writing, supervision, and funding roles.
- Sanitized code and data are available to reviewers on request from the
  corresponding author. Public release is planned; the repository remains
  private while its separate sensitive-data removal request is pending.

The manuscript imports [`author-contributions.tex`](author-contributions.tex),
[`competing-interests.tex`](competing-interests.tex), and
[`funding.tex`](funding.tex). Edit these sources when a statement changes.
The data statement and research-code assistance description are in the shared
article, and its artificial intelligence declaration remains before references.

## Build both papers and their current source archives

From the repository root, with Python 3.10 or later, pdfLaTeX, BibTeX,
the article's TeX packages, and `elsarticle-harv.bst` installed:

```bash
python scripts/build_manuscript.py --target all --output /tmp/paper-submission-build
```

Use a new output directory for each build. If the bibliography style is not
installed in the TeX distribution, pass its official file explicitly with
`--bst /path/to/elsarticle-harv.bst`. The output contains the two paper PDFs,
the standalone supplement, fresh flat source archives, build logs, and a
manifest of the packaged inputs and generated artifacts.
The builder operates on the current shared sources, compiles the supplement
before the CACE article, and does not run optimization experiments.
Each source ZIP uses `main.tex` as its submission entry point and includes
`main.bbl`. The CACE archive adds the journal-mode switch to that generated
entry point; both archives take the article text from the same shared source.
Compile `supplementary.tex` before `main.tex` when rebuilding the CACE archive
after editing its supplement. Its packaged labels and supplementary PDF are
generated together with the article.

The arXiv PDF is also retained as `../main.pdf` for existing links.
`../manuscript_sources.zip`, `../joint_comparison.pdf`, and older verification
manifests describe historical snapshots. Do not upload them as this paper's
current source bundle.

## Editable submission documents

- [`Highlights.docx`](Highlights.docx), generated from [`highlights.txt`](highlights.txt).
  The five highlights have 82, 84, 81, 82, and 79 characters, including spaces.
- [`Cover-letter.docx`](Cover-letter.docx), generated from [`cover-letter.txt`](cover-letter.txt).
  Update its date to the actual submission date before use.
- [`Declaration-of-competing-interests.docx`](Declaration-of-competing-interests.docx),
  generated from the same prose the manuscript imports.

Regenerate these documents after editing their sources:

```bash
python scripts/export_submission_documents.py --output manuscript/submission
```

The exporter uses Python's standard library. Upload each document under the
appropriate item type in the journal portal. If the portal requires its own
declaration template or declaration-tool output, transfer the confirmed statement
there rather than treating the supplied Word document as that official form.

## Publisher requirements and remaining journal-specific checks

The abstract supplied by the corresponding author is 249 words. Its wording
is shared by both paper versions. The author contributions, competing interests,
funding, data availability, and artificial intelligence disclosures are included
in both versions.

Elsevier's [highlights instructions](https://www.elsevier.com/researcher/author/tools-and-resources/highlights)
specify three to five bullets of at most 85 characters, without acronyms.
The [author-contribution guidance](https://www.elsevier.com/researcher/author/policies-and-guidelines/credit-author-statement)
calls for agreed descriptions of each author's roles.
The [artificial intelligence policy](https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals)
requires manuscript-preparation disclosure and a Methods description of research
and data-visualization assistance. These disclosures describe the tools already
acknowledged in the paper, rather than a new experimental method.
The [LaTeX instructions](https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions)
explain the PDF/source upload categories and require a flat source-file layout
for Editorial Manager.

The current [CACE Guide for Authors](https://www.sciencedirect.com/journal/computers-and-chemical-engineering/publish/guide-for-authors)
returned HTTP 403 during the November 3, 2026 audit. Before submitting, check
the live guide and portal for the exact abstract and keyword limits, whether
a graphical abstract is required, the review/anonymization format, any mandatory
template, the declaration-tool format, and the journal's specific data policy.
A graphical abstract is not included in this preparation. This is a prepared
submission package, not certification of the unverified journal-specific rules.

Elsevier's [publication policy](https://www.elsevier.com/about/policies-and-standards/publishing-ethics)
does not treat electronic preprints as prior journal publication. Posting the
arXiv version later is separate from submitting the journal version; these files
do not perform either submission or change repository visibility.
