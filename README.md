# codecommit-cli
AWS CodeCommit CLI

## Usage

```
$ ccc -h
usage: ccc [-h] {repos,prs} ...

positional arguments:
  {repos,prs}
    repos      list repos
    prs        list PRs for repo

optional arguments:
  -h, --help   show this help message and exit
```

## Command Line Completion Installation

codecommit-cli uses argcomplete for commandline completion, see https://kislyuk.github.io/argcomplete/#installation

### Zsh

Add the following to your ~/.zshrc file and start new terminal window once saved

```
autoload -U bashcompinit
bashcompinit
eval "$(register-python-argcomplete ccc)"
```

### Bash

Add following to ~/.bash_profile and start new terminal window once saved

```
eval "$(register-python-argcomplete ccc)"
```


## License
The license is Apache 2.0, see [LICENSE](./LICENSE) for the details.