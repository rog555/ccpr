# AWS CodeCommit PR CLI

The **ccpr** script attempts to replicate the basic AWS CodeCommit Console from the CLI when dealing with pull requests

This is achieved via context of current working git repo and branch, a bit of commandline completion and rich colours!

**why?**

Using CodeCommit console in one account at same time as accessing console in another account can be a pain (yes, maybe incognito could work..)  CLI access should allow for quicker workflow for creating/reviewing/approving and merging PRs

## Usage

```
usage: ccpr [-h]
            {approve,a,create,c,close,x,comment,C,diff,d,merge,m,pr,id,prs,ls,repos,r}
            ...

AWS CodeCommit PR CLI

positional arguments:
  {approve,a,create,c,close,x,comment,C,diff,d,merge,m,pr,id,prs,ls,repos,r}
    approve (a)         approve PR
    create (c)          create PR
    close (x)           close PR
    comment (C)         comment on PR, general if file and lineno not
                        specified
    diff (d)            diff two local files
    merge (m)           merge PR
    pr (id)             show details for specific PR (colorized diffs with
                        comments etc)
    prs (ls)            list PRs for repo
    repos (r)           list repos

optional arguments:
  -h, --help            show this help message and exit
```

## Installation

Until ccpr is available on pip, clone this repo and then symlink ccpr.py to somewhere on your PATH

Eg:

```
$ git clone https://github.com/rog555/codecommit-pr-cli.git
$ ln -s codecommit-pr-cli/ccpr.py /usr/local/bin/ccpr
$ pip install -r codecommit-pr-cli/requirements.txt
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
export AWS_PROFILE=devops-account
export AWS_REGION=us-east-1
```

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

## License
The license is Apache 2.0, see [LICENSE](./LICENSE) for the details.