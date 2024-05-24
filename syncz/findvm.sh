#!/bin/bash

# Check if VM name is provided as an argument
if [ $# -eq 0 ]; then
    echo "Usage: $0 <VM_NAME>"
    exit 1
fi

hosts=("172.16.1.11" "172.16.1.28" "172.16.1.10")

found=false
for host in "${hosts[@]}"; do
    vm_info=$(ssh root@$host "vim-cmd vmsvc/getallvms | grep -i '$1'")

    if [ -n "$vm_info" ]; then
        found=true
        datastore_line=$(echo "$vm_info" | awk -F ']' '{print $1}')
        datastore=$(echo "$datastore_line" | awk -F '[' '{print $2}' | awk '{$1=$1};1')
        symlink=$(ssh root@$host "ls -l /vmfs/volumes/$datastore")
        datastore_link="/vmfs/volumes/$(echo "$symlink" | awk '{print $NF}')"
        extra_path=$(echo "$datastore_line" | awk -F ' ' '{print $2}' | awk -F '/' '{print $1}')
        datastore_path="$datastore_link/$extra_path/"
        vmid=$(echo "$vm_info" | awk '{print $1}')
        filename="$1.tar.zst"

        echo "$host"
        echo "$datastore_path"
        echo "$filename"
        echo "$vmid"
    fi
done

if [ "$found" == false ]; then
    echo "VM with name '$1' not found on any of the hosts."
fi
