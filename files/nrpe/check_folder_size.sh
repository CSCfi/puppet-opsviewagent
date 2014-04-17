#!/bin/bash
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#

USAGE="Usage $0 -f dir [-s (k|m|g)] [-w (size)] [-c (size)]"

folder=`pwd` 
divisor=1
unidad="KB"
warning=0
critical=0
BC=/usr/bin/bc

if [ "$#" == "0" ]; then 
	echo "$USAGE"
	exit 3
fi

FOLDER(){
  if [ -d "$1" ];then folder=$1 && return;else
  echo "ERROR: Folder is invalid"
  exit 1
  fi
  folder=$1
  return	
}

MU(){
 case "$1" in
	[Kk])
	  divisor=1
	  unidad="KB"
	  return
	;;
	[Mm])
	  divisor=1024
	  unidad="MB"
	  return
	;;
	[Gg])
	  divisor=1048576
	  unidad="GB"
	  return
	;;
	*)
	 echo "Please use:"
	 echo "k for Kilobytes(KB) data"
         echo "m for Megabytes (MB) data"
	 echo "g for Gigabytes (GB) data"
	 exit 3
 esac
}

OK(){
echo "OK: The folder size is $size$unidad|size=$size$unidad"
exit 0
}
WARNING(){
echo "WARNING: The folder size is $size$unidad|size=$size$unidad"
exit 1
}
CRITICAL(){
echo "CRITICAL: The folder size is $size$unidad|size=$size$unidad"
exit 2
}


while (( $# )); do

case "$1" in
	--help)
	echo $USAGE
	exit 3
	;;
	-h)
	echo $USAGE
	exit 3
	;;
	-f)
	FOLDER $2	
	;;
	-s)
	MU $2
	;;
	-w)
	declare -i warning=$2
	w0="0"
	if [ $warning -gt 0 ];then 
	w0="1"
	fi
	;;
	-c)
	declare -i critical=$2
	c0="0"
	if [ $critical -gt 0 ];then
        c0="2"
        fi
	;;
	*)
 	echo "$USAGE"
esac

shift
shift

done


size=`du --max-depth=1 $folder|tail -1 |awk -v DIVISOR=$divisor '{print $1/DIVISOR}'`

let wc0=$(($critical>$warning?0:4))
let wc1=$(($c0+$w0+$wc0))
let wc2=$((`echo "$size>$warning"|$BC`))
let wc3=$((`echo "$size>$critical"|$BC`))

case $wc1 in
	0)
	OK
	;;
	1)
	if (( $wc2 == 1 )); then
	WARNING
	else
	OK
	fi
	;;
	2)
	if (( $wc3 == 1 )); then
        CRITICAL
        else
        OK
        fi
	;;
	3)
	if (( $wc3 == 1 )); then
        CRITICAL
        elif (( $wc2 == 1 )); then
        WARNING
	else
	OK
        fi
	;;
	5)
        if (( $wc2 == 1 )); then
        WARNING
        else
        OK
        fi
	;;
	46789)
	echo $USAGE	
	exit 3
	;;
	*)
	echo $USAGE
	exit 3

esac
