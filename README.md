# AWS CodeCommit PR CLI

The **ccpr** script attempts to replicate the basic AWS CodeCommit Console from the CLI when dealing with pull requests.  It does abit more such as enable recursive remote repo searches and CodePipeline build status/linking

This is achieved via context of current working git repo and branch, a bit of commandline completion and rich colours!

**why?**

Using CodeCommit console in one account at same time as accessing console in another account can be a pain (yes, maybe incognito could work..)  CLI access should allow for quicker workflow for creating/reviewing/approving and merging PRs

[![Tests](https://github.com/rog555/ccpr/actions/workflows/tests.yml/badge.svg)](https://github.com/rog555/ccpr/actions/workflows/tests.yml/)
[![Codecov](https://codecov.io/gh/rog555/ccpr/branch/main/graph/badge.svg)](https://codecov.io/gh/rog555/ccpr/branch/main)

## Usage

```
usage: ccpr [-h] {approve,a,create,c,close,x,comment,C,diff,d,grep,g,merge,m,pipeline,p,pr,id,prs,ls,repos,r} ...

AWS CodeCommit PR CLI

positional arguments:
  {approve,a,create,c,close,x,comment,C,diff,d,grep,g,merge,m,pipeline,p,pr,id,prs,ls,repos,r}
    approve (a)         approve PR
    create (c)          create PR
    close (x)           close PR
    comment (C)         comment on PR, general if file and lineno not specified
    diff (d)            diff two local files
    grep (g)            grep the remote repo(s)
    merge (m)           merge PR
    pipeline (p)        show codepipeline status
    pr (id)             show details for specific PR (colorized diffs with comments etc)
    prs (ls)            list PRs for repo - OPEN by default
    repos (r)           list repos

optional arguments:
  -h, --help            show this help message and exit
```

## Installation

```
$ pip install ccpr
```

ccpr uses argcomplete for commandline completion, see https://kislyuk.github.io/argcomplete/#installation

### Zsh

Add the following to your ~/.zshrc file and start new terminal window once saved

```
autoload -U bashcompinit
bashcompinit
eval "$(register-python-argcomplete ccpr)"
```

### Bash

Add following to ~/.bash_profile and start new terminal window once saved

```
eval "$(register-python-argcomplete ccpr)"
```

## Authentication ##

See https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html

Eg: 

```
export AWS_DEFAULT_PROFILE=devops-account
export AWS_DEFAULT_REGION=us-east-1
```

If using SAML with Azure, then something like https://github.com/Versent/saml2aws might help

## Examples

### List repos

```
$ ccpr repos -f tool
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ name                                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ developer-tools                      │
│ monitoring-tools                     │
│ some-other-tool                      │
└──────────────────────────────────────┘
```

### Create PR

Change to CodeCommit repo directory and create PR on the 'foobar' branch.  The latest commit message is used as default PR title

```
$ cd developer-tools/
$ git branch
  master
* foobar

$ ccpr create
Enter PR title (foobar baz biz fiz):
created PR 351
link: https://us-east-1.console.aws.amazon.com/codesuite/codecommit/repositories/developer-tools/pull-requests/351/changes?region=us-east-1
```

### List PRs in current repo

```
$ ccpr prs
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ id  ┃ title              ┃ author        ┃ activity    ┃ status ┃ approvals              ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 351 │ foobar baz biz fiz │ foo@foo.com   │ 3 hours ago │ CLOSED │ 1 of 2 rules satisfied │
└─────┴────────────────────┴───────────────┴─────────────┴────────┴────────────────────────┘
```

### List details of PR

Show colorized diff

```
$ ccpr pr 351 -d
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ id  ┃ title              ┃ author        ┃ activity    ┃ status ┃ approvals              ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 351 │ foobar baz biz fiz │ foo@foo.com   │ 3 hours ago │ CLOSED │ 1 of 2 rules satisfied │
└─────┴────────────────────┴───────────────┴─────────────┴────────┴────────────────────────┘
some-file1.txt
────────────────────────────────────────────────────────────────────────────────────────────
   1    1:   abc
   2     : - def
        2: + defghi
   3     : - hij
        3: + xyz
        4: +
```

### Recursive grep across remote repos

```
$ ccpr grep -R -i baz '*.txt' --repo 'myrepo1,somerepo*'
myrepo1: /folder1/somefile1.txt:    fooBar
somerepo1: /folder1/somefile3.txt:    fooBar
somerepo1: /folder2/somefile4.txt:    FOOBAR
```


### Show Code Pipeline status

Depends how pipeline setup, but a sensible generic convention could be
in format `<repo>_<branch>`, if not use the `--name` option

Use `-m` for `master` branch, current repo will be used without `--name`

The `-c` argument will show commits which can be clicked on linking to AWS


```
$ ccpr pipeline -m -c
link: https://us-east-1.console.aws.amazon.com/codesuite/codepipeline/pipelines/
repo1_master/view?region=us-east-1
┏━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ stage   ┃ status     ┃ updated         ┃ commit    ┃ summary         ┃ error ┃
┡━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ source  │ Succeeded  │ 2 hours ago     │ #34567890 │ fix something   │       │
│ build   │ Succeeded  │ 2 hours ago     │ #34567890 │                 │       │
│ approve │ Succeeded  │ 2 hours ago     │ #34567890 │ Approved by     │       │
│ test    │ Failed     │ 2 hours ago     │ #34567890 │                 │ ohno! │
│ deploy  │ InProgress │ 4 hours ago     │ #99999999 │ InProgress...   │       │
│ deploy  │ Succeeded  │ 4 hours ago     │ #99999999 │                 │       │
└─────────┴────────────┴─────────────────┴───────────┴─────────────────┴───────┘
commits:
┏━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ # ┃ commit    ┃ updated             ┃ build     ┃ summary  ┃
┡━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ 1 │ #34567890 │ 2020-01-01 00:00:00 │ #34567890 │ foo      │
│ 2 │ #99999999 │ 2020-01-01 00:00:00 │ #99999999 │ bar      │
└───┴───────────┴─────────────────────┴───────────┴──────────┘
```

## License

The license is Apache 2.0, see [LICENSE](./LICENSE) for the details.