#!/bin/bash

title "Deploy compose project for industrial line 1 "

docker compose --env-file ../industrial_line.env -f ../industrial_line.yml -p "industrial_line1" up -d
