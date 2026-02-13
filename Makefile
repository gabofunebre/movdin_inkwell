# Helper Makefile para desarrollo y automatización

APP_SVC ?= app
DOCKER_COMPOSE ?= docker compose
MSG ?= update

.PHONY: help up down down-v start stop restart ps logs shell rebuild rebuild-v push pull prune run backup restore deploy smoke

help:
	@echo "Comandos disponibles:"
	@echo "  make up        - Levanta los contenedores con build"
	@echo "  make down      - Detiene y elimina los contenedores"
	@echo "  make down-v    - Idem down, pero elimina también los volúmenes"
	@echo "  make restart   - Reinicia el contenedor principal"
	@echo "  make start     - Inicia el contenedor principal si está detenido"
	@echo "  make stop      - Detiene el contenedor principal"
	@echo "  make ps        - Lista contenedores activos"
	@echo ""
	@echo "Logs y shell:"
	@echo "  make logs      - Muestra logs de todos los contenedores"
	@echo "  make shell     - Abre una shell bash en el contenedor principal"
	@echo ""
	@echo "Rebuild:"
	@echo "  make rebuild   - Baja y vuelve a levantar los contenedores"
	@echo "  make rebuild-v - Idem rebuild, eliminando también volúmenes"
	@echo ""
	@echo "Git:"
	@echo "  make push MSG='msg' - Hace commit y push con mensaje"
	@echo "  make pull           - Hace pull desde main"
	@echo ""
	@echo "Utilidades:"
	@echo "  make prune    - Limpia recursos docker sin usar"
	@echo "  make run cmd  - Ejecuta un comando dentro del contenedor principal (ej: make run ls -la)"

	@echo ""
	@echo "Operación de datos y despliegue:"
	@echo "  make backup                - Genera dump lógico de la DB en ./backups"
	@echo "  make restore DUMP=archivo  - Restaura un dump sobre la DB del entorno actual"
	@echo "  make deploy DUMP=archivo   - Update git + restore + arranque app + smoke test"
	@echo "  make smoke                 - Verifica salud de la app en /health"

# Contenedores
up:
	$(DOCKER_COMPOSE) up --build -d

down:
	$(DOCKER_COMPOSE) down

down-v:
	$(DOCKER_COMPOSE) down -v

start:
	$(DOCKER_COMPOSE) start $(APP_SVC)

stop:
	$(DOCKER_COMPOSE) stop $(APP_SVC)

restart:
	$(DOCKER_COMPOSE) restart $(APP_SVC)

ps:
	$(DOCKER_COMPOSE) ps

# Logs y shell
logs:
	-$(DOCKER_COMPOSE) logs -f || true

shell:
	$(DOCKER_COMPOSE) exec $(APP_SVC) /bin/bash

# Rebuild
rebuild:
	$(MAKE) down
	$(MAKE) up

rebuild-v:
	$(MAKE) down-v
	$(MAKE) up

# Git
push:
	git add .
	git commit -m "$(MSG)" || true
	git push

pull:
	git pull origin main

# Utilidades
prune:
	docker system prune

# Ejecutar comando dentro del contenedor
run:
	$(DOCKER_COMPOSE) exec $(APP_SVC) $(filter-out $@,$(MAKECMDGOALS))

# Target wildcard
%:
	@:


# Operación de datos y despliegue
backup:
	bash scripts/backup_db.sh

restore:
	@test -n "$(DUMP)" || (echo "Uso: make restore DUMP=./backups/archivo.dump" && exit 1)
	docker compose up -d db
	set -a; [ -f .env ] && . ./.env; set +a; \
	cat "$(DUMP)" | docker compose exec -T db pg_restore -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --clean --if-exists --no-owner

deploy:
	@test -n "$(DUMP)" || (echo "Uso: make deploy DUMP=./backups/archivo.dump [REF=main]" && exit 1)
	bash scripts/restore_and_deploy.sh "$(DUMP)" "$(if $(REF),$(REF),main)"

smoke:
	curl -fsS http://localhost:8000/health >/dev/null && echo "Smoke test OK"
