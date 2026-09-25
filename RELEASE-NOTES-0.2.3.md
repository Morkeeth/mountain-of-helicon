# Mountain of Helicon 0.2.3

- New: `helicon review --html` writes a one-page report with the grade, the three worst
  problems, and a button that copies each fix. The default page is
  `helicon-review.html` inside the reviewed repo. `--html PATH` writes it where you choose.
- New: `helicon fix` prints safe rewrites for a path that moved. A rewrite is safe only when
  exactly one file in the repo has that name. It is a dry run. It writes only with `--apply`.
- Neither command writes through a symlink. The report and `fix --apply` open every file
  from a directory handle on the repo root, and they refuse a link at any step. A repo that
  plants `helicon-review.html` as a link to a file in your home folder cannot make the
  review overwrite that file. A link inside the repo, such as `CLAUDE.md` pointing to
  `AGENTS.md`, is still fixed through its target.
