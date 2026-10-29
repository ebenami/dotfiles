# Preferred editor for local and remote sessions
if [[ -n $SSH_CONNECTION ]] || ! (( $+commands[mvim] )); then
  export EDITOR='vim'
else
  export EDITOR='mvim'
fi

#docker cleanup
alias docker-rm-exited='docker rm -v $(docker ps -a -q -f status=exited)'
alias docker-rm-dangling='docker rmi $(docker images -f "dangling=true" -q)'
alias docker-rm-volume='docker volume rm $(docker volume ls -qf dangling=true)'
alias docker-cleanup='docker container prune --force; docker-rm-exited; docker-rm-dangling; docker-rm-volume'

alias dokcer='docker'

alias vbox-clipboard="pkill 'VBoxClient --clipboard' -f & sleep 1 && VBoxClient --clipboard"

#Docker
function docker-ls-child(){
  docker inspect --format='{{.Id}}' $(docker images --filter since="$@" -q)
}

function nocolor(){
  cat "$@" | sed -E 's/\x1B\[[0-9;]*[mK]//g'
}

#grep
EXCLUDE_FOLDERS="{.bzr,CVS,.git,.hg,.svn,node_modules,site-packages,coverage,mochawesome-report}"
if (( $+commands[ggrep] )); then
  alias grep='ggrep --color=auto'
elif [[ "$OSTYPE" == linux* ]]; then
  alias grep='grep --color=auto'
fi
alias g="grep --exclude-dir=$EXCLUDE_FOLDERS --color "
alias gpy='grep --include="*.py"'
alias gjs='grep --include="*.js" --include="*.json"'
alias clearswp='rm -rf ~/.vim/swapfiles/*'

alias gitl='git l'
alias gitroot='cd $(git rev-parse --show-toplevel)'

(( $+commands[podman] )) && alias docker=podman
[[ "$OSTYPE" == darwin* ]] && alias pycharm='open -a "PyCharm.app" --args'

function pexpackage(){
 echo "unzip -l $1 | grep .deps | cut -d '/' -f 2 | uniq ${@:2}"
 unzip -l $1 | grep .deps | cut -d '/' -f 2 | uniq ${@:2}
}

