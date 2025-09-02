# API de Integración con Salesforce

**Versión:** Beta 1.0

## 1. Resumen Técnico

Esta API actúa como una capa de abstracción (middleware) desarrollada en Python con el framework Flask. Su propósito principal es simplificar y estandarizar las interacciones con la API de Salesforce para agentes de software internos y otros microservicios.

En lugar de que cada servicio cliente implemente su propia lógica para autenticarse, construir consultas SOQL y manejar la API de Salesforce, esta aplicación centraliza dichas operaciones, ofreciendo una serie de endpoints RESTful limpios y orientados a tareas específicas.

### Arquitectura y Stack Tecnológico

- **Lenguaje:** Python 3.12
- **Framework:** Flask
- **Servidor WSGI:** Gunicorn (para producción)
- **Librería Salesforce:** `simple-salesforce`
- **Autenticación con Salesforce:** Flujo JWT Bearer Token, utilizando una clave de consumidor y un archivo de clave privada (`server.key`).
- **Contenerización:** Docker
- **Despliegue y CI/CD:** Google Cloud Run, con compilaciones automáticas gestionadas por Google Cloud Build y almacenamiento de imágenes en Google Artifact Registry.
- **Gestión de Secretos:** Google Secret Manager para almacenar de forma segura las credenciales de producción.

---

## 2. Documentación de Endpoints (Beta 1.0)

Todos los endpoints esperan y devuelven datos en formato `application/json`.

### Contactos

#### `POST /contact/find`
- **Descripción:** Busca un único contacto en Salesforce por su nombre completo.
- **Payload (Request):**
  ```json
  {
    "full_name": "Juan Pérez"
  }
  ```
- **Respuesta Exitosa (200 OK):**
  ```json
  {
    "status": "found",
    "contact": {
      "Id": "003...",
      "FirstName": "Juan",
      "LastName": "Pérez",
      "Email": "juan.perez@example.com",
      "AccountId": "001..."
    }
  }
  ```
- **Respuesta No Encontrado (404 Not Found):**
  ```json
  {
    "status": "not_found",
    "message": "Contacto con nombre 'Juan Pérez' no encontrado."
  }
  ```

#### `POST /contact/create`
- **Descripción:** Crea un nuevo contacto. Un Flow en Salesforce se encarga de crear y asociar una cuenta automáticamente. La API intenta vincular el `AccountId` al contacto recién creado.
- **Payload (Request):**
  ```json
  {
    "full_name": "Ana García",
    "Email": "ana.garcia@example.com"
  }
  ```
- **Respuesta Exitosa (201 Created):**
  ```json
  {
    "status": "created",
    "contact": {
      "Id": "003...",
      "FirstName": "Ana",
      "LastName": "García",
      "Email": "ana.garcia@example.com",
      "Entity_Type__c": "Individual",
      "AccountId": "001..."
    }
  }
  ```

#### `POST /contact/verify/dob`
- **Descripción:** Verifica la existencia de un contacto usando su nombre completo y fecha de nacimiento.
- **Payload (Request):**
  ```json
  {
    "full_name": "Juan Pérez",
    "dob": "1990-05-15"
  }
  ```
- **Respuesta Exitosa (200 OK):**
  ```json
  {
    "status": "verified",
    "contact": {
      "Id": "003...",
      "FirstName": "Juan",
      "LastName": "Pérez",
      "DOB__c": "1990-05-15"
    }
  }
  ```

#### `POST /contact/verify/dob-phone`
- **Descripción:** Verifica un contacto usando nombre completo, fecha de nacimiento y número de teléfono. La comparación del teléfono ignora caracteres de formato.
- **Payload (Request):**
  ```json
  {
    "full_name": "Juan Pérez",
    "dob": "1990-05-15",
    "phone": "(555) 123-4567"
  }
  ```
- **Respuesta Exitosa (200 OK):**
  ```json
  {
    "status": "verified",
    "contact": {
      "Id": "003...",
      "FirstName": "Juan",
      "LastName": "Pérez",
      "DOB__c": "1990-05-15",
      "Phone": "(555) 123-4567"
    }
  }
  ```

### Casos y Servicios

#### `POST /customer_service/create`
- **Descripción:** Crea un registro de `Customer_Service__c`.
- **Payload (Request):**
  ```json
  {
    "AccountId": "001...",
    "CallType__c": "Inbone",
    "ParentezcoDelCliente__c": "Cliente",
    "Fast_Note__c": "El cliente llamó para consultar sobre su caso.",
    "UltimoAnioDeAyuda__c": "2024",
    "Communication_channel__c": "Phone",
    "TipoCliente__c": "Cliente Retorno",
    "TipoHumor_Cliente__c": "Calmado"
  }
  ```
- **Respuesta Exitosa (201 Created):**
  ```json
  {
    "status": "created",
    "customer_service": {
      "Id": "a00...",
      "AccountId": "001...",
      "CallType__c": "Inbone",
      "ParentezcoDelCliente__c": "Cliente",
      "Fast_Note__c": "El cliente llamó para consultar sobre su caso.",
      "UltimoAnioDeAyuda__c": "2024",
      "Communication_channel__c": "Phone",
      "TipoCliente__c": "Cliente Retorno",
      "TipoHumor_Cliente__c": "Calmado"
    }
  }
  ```

#### `POST /script_case`
- **Descripción:** Crea un registro de `Script_Case__c`, asociándolo a un Contacto o a una Cuenta.
- **Payload (Request):**
  ```json
  {
    "ContactId": "003...",
    "X5_0_Estado_Civil__c": "Soltero",
    "X5_1_Ingreso_Mensual__c": 5000
  }
  ```
- **Respuesta Exitosa (201 Created):**
  ```json
  {
    "status": "created",
    "case": {
      "Id": "a01...",
      "ContactId": "003...",
      "X5_0_Estado_Civil__c": "Soltero",
      "X5_1_Ingreso_Mensual__c": 5000
    }
  }
  ```

---

## 3. Configuración y Despliegue

### Archivos de Configuración

- **`Dockerfile`**: Define las instrucciones para construir la imagen de contenedor de la aplicación. Utiliza una imagen base de Python, instala las dependencias y establece el comando de inicio con Gunicorn.
- **`requirements.txt`**: Lista las dependencias de Python necesarias para el proyecto.
- **`cloudbuild.yaml`**: Archivo de configuración para Google Cloud Build. Define un pipeline de CI/CD que se activa con un `git push`. Los pasos son:
  1.  Construir la imagen de Docker.
  2.  Subir la imagen a Google Artifact Registry.
  3.  Desplegar la nueva imagen en el servicio de Google Cloud Run, inyectando los secretos correspondientes.
- **`.env` (Solo para desarrollo local)**: Este archivo **no debe subirse a Git**. Contiene las variables de entorno para ejecutar la aplicación localmente.
  ```
  SF_USERNAME="tu_usuario@salesforce.com"
  SF_CONSUMER_KEY="tu_consumer_key"
  SF_PRIVATE_KEY_FILE="server.key"
  SF_DOMAIN="test"
  ```
- **`server.key` (Solo para desarrollo local)**: La clave privada para la autenticación JWT. **Nunca debe subirse a Git**.

### Despliegue para un Nuevo Agente o Servicio

El proyecto está configurado para despliegue continuo. Para replicar o crear una nueva instancia de esta API para otro propósito, sigue estos pasos:

#### 1. Prerrequisitos
- Acceso a un proyecto de Google Cloud.
- `gcloud` CLI instalado y autenticado.
- Repositorio Git clonado.

#### 2. Configuración en Google Cloud
1.  **Habilitar APIs:** Asegúrate de que las siguientes APIs estén habilitadas en tu proyecto de GCP:
    - `run.googleapis.com` (Cloud Run)
    - `cloudbuild.googleapis.com` (Cloud Build)
    - `artifactregistry.googleapis.com` (Artifact Registry)
    - `secretmanager.googleapis.com` (Secret Manager)

2.  **Crear Secretos:** Almacena las credenciales de Salesforce en Secret Manager. Los nombres de los secretos deben coincidir con los definidos en `cloudbuild.yaml`.
    ```bash
    # Ejemplo para el usuario
    gcloud secrets create sf-prod-username --replication-policy="automatic"
    echo -n "TU_USUARIO_SALESFORCE" | gcloud secrets versions add sf-prod-username --data-file=-

    # Ejemplo para la clave privada
    gcloud secrets create sf-prod-private-key --replication-policy="automatic"
    gcloud secrets versions add sf-prod-private-key --data-file="ruta/a/tu/server.key"
    ```
    *Repite este proceso para `sf-prod-consumer-key` y `sf-prod-domain`.*

3.  **Crear Repositorio de Artefactos:** Crea un repositorio en Artifact Registry para almacenar las imágenes de Docker.
    ```bash
    gcloud artifacts repositories create api-salesforce-repo \
      --repository-format=docker \
      --location=us-central1
    ```

#### 3. Configuración del Despliegue
1.  **Ajustar `cloudbuild.yaml` (Opcional):** Si deseas desplegar un servicio con un nombre diferente, modifica el argumento `api-salesforce-service` en el último paso del archivo `cloudbuild.yaml`.

2.  **Crear Disparador de Cloud Build:**
    - En la consola de Google Cloud, ve a `Cloud Build` > `Disparadores`.
    - Conecta tu repositorio de GitHub.
    - Crea un nuevo disparador que se active al hacer `push` a la rama `main`.
    - En la configuración del disparador, selecciona "Archivo de configuración de Cloud Build" y asegúrate de que apunte a `/cloudbuild.yaml`.

Una vez configurado, cada `git push` a la rama `main` iniciará automáticamente el proceso de build y despliegue en Cloud Run.
