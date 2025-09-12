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
