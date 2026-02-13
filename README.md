# Movdin

Aplicación web basada en FastAPI para registrar movimientos de dinero y facturación.

## Características

- **Cuentas:** Cada cuenta tiene nombre, moneda, saldo inicial, color y puede marcarse como cuenta de facturación.
- **Transacciones:** Se pueden registrar ingresos y egresos asociados a una cuenta.
- **Facturas:** Para la cuenta de facturación se cargan facturas de compra y venta. El sistema calcula automáticamente IVA e IIBB.
- **Transacciones frecuentes:** Plantillas para agilizar carga de movimientos repetitivos.
- **Usuarios y permisos:** Registro de usuarios, inicio de sesión, aprobación por administrador y roles de administrador.

## Guía rápida de uso

1. Regístrate con tu correo y espera la aprobación de un administrador.
2. Crea tus cuentas indicando nombre, moneda y saldo inicial.
3. Registra ingresos y egresos desde la sección de transacciones.
4. Si corresponde, carga facturas de compra y venta en la cuenta de facturación.
5. Aprovecha las transacciones frecuentes para movimientos repetitivos.

Consulta [USAGE.md](USAGE.md) para una guía más detallada.

## Integración entre aplicaciones

La aplicación expone un endpoint pensado para que otras apps consuman la
información fiscal consolidada:

- **GET `/facturacion-info`**
  - **Autenticación:** enviar el encabezado `X-API-Key` con el valor de la
    variable de entorno `SELF_BILLING_API_KEY`.
  - **Respuesta:** se devuelve un JSON con dos colecciones: `invoices` con las
    facturas de la cuenta marcada como "de facturación" y
    `retention_certificates` con los certificados de retención asociados. Cada
    elemento incluye todos los datos necesarios para su liquidación (fechas,
    importes netos, impuestos calculados y números de referencia).
  - **Ejemplo de respuesta**:

    ```json
    {
      "invoices": [
        {
          "id": 12,
          "account_id": 3,
          "date": "2024-01-15",
          "description": "Factura de servicios",
          "amount": "100000.00",
          "number": "A-0001-00001234",
          "iva_percent": "21",
          "iva_amount": "21000.00",
          "iibb_percent": "3",
          "iibb_amount": "3630.00",
          "percepciones": "0.00",
          "type": "sale"
        }
      ],
      "retention_certificates": [
        {
          "id": 5,
          "number": "RC-00000001",
          "date": "2024-01-31",
          "invoice_reference": "A-0001-00001234",
          "retained_tax_type_id": 2,
          "amount": "1500.00",
          "retained_tax_type": {
            "id": 2,
            "name": "Retención de IVA"
          }
        }
      ]
    }
    ```

  Las otras aplicaciones pueden usar el campo `invoice_reference` de cada
  certificado para relacionarlo con la factura correspondiente.

### Sincronización de movimientos de facturación

- `transaction_events` es la fuente de verdad para aplicar cambios (`created`,
  `updated`, `deleted`) y evita "movimientos fantasma", porque cada alta,
  modificación o baja se materializa solo cuando llega su evento explícito.
- `transactions` se usa como snapshot auxiliar de contexto, pero no define por
  sí solo el estado final local.
- Las altas/cambios/bajas en Movdin se derivan exclusivamente de
  `transaction_events`, procesados en orden por identificador de evento.
- El ACK se envía al final, después de persistir y confirmar localmente la
  tanda procesada; así, si algo falla antes del commit o del ACK, la próxima
  sincronización puede reintentar de forma segura sin perder consistencia.

## Cálculos de moneda

- **Saldo de cuentas:** El saldo de cada cuenta se calcula como `saldo_inicial + suma(transacciones)` para la fecha indicada.
- **Ajustes por facturación:** Si la cuenta es de facturación, el saldo neto descuenta IVA e IIBB de las ventas y suma el IVA de las compras.
- **Facturas:** Al crear o editar una factura se calcula automáticamente el IVA (`monto * porcentaje/100`) y, si es una venta, el IIBB sobre el monto más el IVA (`(monto + iva) * porcentaje/100`).
- Los montos se almacenan usando `Decimal` con dos decimales y no se realiza conversión automática entre monedas; los saldos se informan en la moneda de cada cuenta.

## Desarrollo con Docker

1. Copiar `.env.example` a `.env` y ajustar los valores según sea necesario, incluyendo `POSTGRES_DATA_PATH` que debe apuntar al directorio persistente de la base de datos (por ejemplo `/tuAlmacenamiento/Servicios/tu_app/postgres_data`).
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

La aplicación también se une a la red externa `cloudflared_net` para poder ser accesible desde otros servicios. Utiliza `docker compose exec` u otros contenedores para interactuar con los servicios.

## Operación: backup, restore y deploy entre servidores

Este proyecto incluye scripts para migrar datos entre servidores y actualizar
la app al commit más reciente sin perder información.

### Conceptos rápidos

- **Dump**: backup lógico de PostgreSQL (archivo `.dump`) generado con `pg_dump`.
- **Restore**: carga de ese dump en otra base de datos con `pg_restore`.
- **Smoke test**: verificación rápida post-deploy para comprobar que la app
  responde (por ejemplo, endpoint `/health`).

### Scripts disponibles

- `scripts/backup_db.sh`
  - Se ejecuta en el servidor origen (actual/productivo).
  - Detiene temporalmente `app`, genera dump lógico y vuelve a iniciar `app`.
  - Salida por defecto: `./backups/movdin_YYYYMMDD_HHMMSS.dump`.

- `scripts/restore_and_deploy.sh <ruta_dump> [ref_git]`
  - Se ejecuta en el servidor destino.
  - Actualiza código (`main` por defecto), levanta DB, restaura dump, levanta app y corre smoke test en `/health`.

> Importante: el transporte del archivo `.dump` entre servidores corre por tu
> cuenta (por ejemplo con `scp` o `rsync`).

### Flujo recomendado

1. En servidor origen:

   ```bash
   make backup
   ```

2. Transferir dump al servidor destino:

   ```bash
   scp ./backups/movdin_YYYYMMDD_HHMMSS.dump usuario@servidor-nuevo:/ruta/
   ```

3. En servidor destino, restaurar y desplegar:

   ```bash
   make deploy DUMP=/ruta/movdin_YYYYMMDD_HHMMSS.dump REF=main
   ```

4. Smoke test manual opcional:

   ```bash
   make smoke
   ```

### Comandos Makefile agregados

- `make backup`
- `make restore DUMP=./backups/archivo.dump`
- `make deploy DUMP=./backups/archivo.dump [REF=main]`
- `make smoke`

### Nota para replicar la misma operatoria en una app hermana

Podés aplicar exactamente la misma idea en otro repositorio:

1. Crear `scripts/backup_db.sh` y `scripts/restore_and_deploy.sh` adaptando
   nombres de servicios Docker Compose y endpoint de smoke test.
2. Agregar objetivos `backup`, `restore`, `deploy`, `smoke` al `Makefile`.
3. Documentar el flujo en README con los mismos pasos (backup → transporte → restore/deploy → smoke).

Prompt sugerido para Codex en la app hermana:

```text
Necesito replicar en este repo la operatoria de migración que usamos en Movdin:
1) crear scripts scripts/backup_db.sh y scripts/restore_and_deploy.sh,
2) agregar targets backup/restore/deploy/smoke al Makefile,
3) actualizar README con una sección Operación (dump/restore/smoke/rollback básico),
4) usar PostgreSQL en docker compose con variables del .env,
5) dejar validaciones robustas y mensajes claros en español.
Luego corré validaciones de sintaxis bash y mostrame los comandos exactos para usar en origen y destino.
```
