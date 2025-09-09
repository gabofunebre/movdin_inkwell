# movdin

Aplicación FastAPI para gestionar movimientos.

## Desarrollo con Docker

1. Copiar `.env.example` a `.env` y ajustar los valores según sea necesario, incluyendo `POSTGRES_DATA_PATH` que debe apuntar al directorio persistente de la base de datos (por ejemplo `/srv/dev-disk-by-uuid-1735d6ab-2a75-4dc4-91a9-b81bb3fda73d/Servicios/adm_TA/postgres_data`).
2. Crear la red externa requerida si aún no existe:

   ```bash
   docker network create cloudflared_net
   ```
3. Levantar los servicios:

   ```bash
   docker compose up --build
   ```

Los contenedores no exponen puertos al host y se comunican entre sí por nombre dentro de la red interna de Docker:

- la aplicación escucha en el puerto `8000` del contenedor `movdin-app`
- PostgreSQL lo hace en el puerto `5432` del contenedor `movdin-db`

La aplicación también se une a la red externa `cloudflared_net` para poder ser accesible desde otros servicios.

Utiliza `docker compose exec` u otros contenedores para interactuar con los servicios.
