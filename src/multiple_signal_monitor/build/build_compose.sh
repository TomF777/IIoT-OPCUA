#!bin/bash
sudo docker compose --env-file ../.env -p "name_of_stack" -f ../docker-compose.yml up --no-recreate --no-start