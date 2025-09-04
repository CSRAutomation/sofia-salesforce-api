from simple_salesforce import Salesforce, SalesforceAuthenticationFailed, SalesforceGeneralError
from flask import Flask, request, jsonify
import os
import time
import datetime
import sys
import threading
import re
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Lógica de Carga de Secretos desde Variables de Entorno ---
# En Cloud Run, estos secretos se inyectan de forma segura desde Secret Manager
# a través de la configuración de despliegue. Para desarrollo local, estas
# variables deben ser exportadas en el entorno de ejecución.

logging.info("Cargando secretos desde variables de entorno...")

SF_USERNAME = os.environ.get("SF_USERNAME")
SF_CONSUMER_KEY = os.environ.get("SF_CONSUMER_KEY")
SF_DOMAIN = os.environ.get("SF_DOMAIN")
SF_PRIVATE_KEY_CONTENT = os.environ.get("SF_PRIVATE_KEY_CONTENT")

# Validar que todas las variables de entorno necesarias estén presentes.
# Esto es crucial para que la aplicación falle rápido si la configuración es incorrecta.
required_secrets = {
    "SF_USERNAME": SF_USERNAME,
    "SF_CONSUMER_KEY": SF_CONSUMER_KEY,
    "SF_DOMAIN": SF_DOMAIN,
    "SF_PRIVATE_KEY_CONTENT": SF_PRIVATE_KEY_CONTENT
}

missing_secrets = [key for key, value in required_secrets.items() if not value]

if missing_secrets:
    error_message = f"Error crítico: Faltan las siguientes variables de entorno: {', '.join(missing_secrets)}"
    logging.critical(error_message)
    sys.exit(1) # Detener la aplicación si no se pueden cargar los secretos

logging.info("Todas las credenciales de Salesforce se han cargado correctamente desde las variables de entorno.")

# --- Inicialización de Flask y Conexión Singleton a Salesforce ---
app = Flask(__name__)
sf_connection = None

# -- Crea la coneccion con salesforce
def get_salesforce_connection():
    """
    Establece y gestiona una conexión singleton con Salesforce.

    Esta función implementa el patrón singleton para la conexión a Salesforce,
    asegurando que solo se cree una instancia de conexión durante el ciclo de
    vida de la aplicación. Esto mejora el rendimiento al reutilizar la
    conexión existente en lugar de crear una nueva para cada solicitud.

    La configuración de la conexión (usuario, clave de consumidor, archivo de
    clave privada y dominio) se obtiene de las variables de entorno.

    Returns:
        simple_salesforce.Salesforce: La instancia de conexión a Salesforce.

    Raises:
        SalesforceAuthenticationFailed: Si las credenciales son incorrectas.
        SalesforceGeneralError: Si ocurre un error general al conectar con la API.
        Exception: Para cualquier otro error inesperado durante la conexión.
    """
    global sf_connection
    if sf_connection is None:
        logging.info("Estableciendo nueva conexión con Salesforce...")
        try:
            sf_connection = Salesforce(
                username=SF_USERNAME,
                consumer_key=SF_CONSUMER_KEY,
                privatekey=SF_PRIVATE_KEY_CONTENT, # Se usa el contenido de la clave directamente
                domain=SF_DOMAIN,
            )
            logging.info("¡Conexión con Salesforce exitosa!")
        except SalesforceAuthenticationFailed as e:
            # Esta excepción tiene .message en lugar de .content
            logging.error(f"Error de autenticación con Salesforce: {e.code} - {e.message}")
            raise
        except SalesforceGeneralError as e:
            logging.error(f"Error de Salesforce al conectar: {e.code} - {e.content}")
            raise
        except Exception as e:
            logging.error(f"Error inesperado durante la conexión: {e}")
            raise
    return sf_connection

def _escape_soql_str(value: str) -> str:
    """
    Escapa una cadena de texto para su uso seguro en una consulta SOQL.

    Esta función toma un valor, lo convierte en cadena, y escapa los caracteres
    especiales (barra invertida y comilla simple) para prevenir la inyección
    de SOQL. Los valores nulos se convierten en la cadena 'NULL'.

    Nota:
        Esta es una implementación de saneamiento básica. Para entornos de
        producción robustos, se recomienda encarecidamente el uso de
        consultas parametrizadas (binding) si la biblioteca lo permite.

    Args:
        value (str): El valor de la cadena a escapar.

    Returns:
        str: La cadena escapada y entre comillas simples, o "NULL".
    """
    if value is None:
        return "NULL"
    return f"'{str(value).replace('\\', '\\\\').replace("'", "\\'")}'"

# --- Funcion encontrar un contacto
@app.route('/contact/find', methods=['POST'])
def find_contact():
    """
    Busca un contacto por nombre completo.
    Espera un JSON: {"full_name": "Nombre Apellido"}
    """
    sf = get_salesforce_connection()
    data = request.json
    full_name = data.get('full_name')

    if not full_name:
        return jsonify({"status": "error", "message": "El campo 'full_name' es requerido."}), 400

    # Se limpia el nombre de espacios extra. La búsqueda se hará sobre el campo
    # compuesto 'Name' de Salesforce, que es más eficiente al estar indexado.
    full_name = full_name.strip()

    try:
        # Se escapa el nombre completo para usarlo de forma segura en la consulta.
        safe_full_name = _escape_soql_str(full_name) # Revertimos a la consulta SOQL original, que es más rápida para este caso.
        # Se modifica la consulta para usar el campo 'Name' en lugar de FirstName y LastName.
        # Esto simplifica la lógica y puede mejorar el rendimiento al usar un único campo indexado.
        query = (
            f"SELECT Id, FirstName, LastName, Email, AccountId FROM Contact WHERE Name = {safe_full_name} LIMIT 1"
        )
        result = sf.query(query)
        logging.info(f"Ejecutando SOQL query: {query}")

        if result.get('totalSize', 0) > 0:
            contact = result['records'][0]
            # Se incluye el AccountId en el log para facilitar la depuración.
            logging.info(f"Contacto encontrado: {contact['Id']}, AccountId: {contact.get('AccountId')}")
            response_data = {"status": "found", "contact": contact}
            status_code = 200
            return jsonify(response_data), status_code
        else:
            logging.info(f"Contacto no encontrado para '{full_name}'.")
            response_data = {"status": "not_found", "message": f"Contacto con nombre '{full_name}' no encontrado."}
            status_code = 404
            return jsonify(response_data), status_code

    except SalesforceGeneralError as e:
        logging.error(f"Error de Salesforce durante la búsqueda: {e.code} - {e.content}")
        return jsonify({"status": "error", "message": "Error de Salesforce.", "details": e.content}), 500
    except Exception as e:
        logging.error(f"Error inesperado durante la búsqueda: {e}")
        return jsonify({"status": "error", "message": "Ocurrió un error inesperado."}), 500

@app.route('/contact/create', methods=['POST'])
def create_contact():
    """
    Crea un nuevo contacto en Salesforce y lo asocia a una cuenta.
    
    Flujo de ejecución:
    1. Recibe los datos del contacto en formato JSON.
    2. Crea el registro del Contacto en Salesforce.
    3. Una automatización (Flow) en Salesforce se activa y crea una Cuenta
       asociada, nombrandola con el nombre y apellido del contacto en mayúsculas.
    4. Esta función espera 5 segundos para dar tiempo a que el Flow se ejecute.
    5. Busca la Cuenta recién creada por su nombre.
    6. Si la encuentra, actualiza el Contacto para asociarle el ID de la Cuenta.
    7. Devuelve los datos del contacto creado, incluyendo el ID de la cuenta si se asoció.

    Espera un JSON con 'LastName' o 'full_name'.
    Ej: {"full_name": "Carlos TEST API", "Email": "carlos.test@example.com"}
    """
    sf = get_salesforce_connection()
    contact_data = request.json

    if not contact_data:
        return jsonify({"status": "error", "message": "El cuerpo de la petición no puede estar vacío."}), 400

    # 1. PREPARACIÓN DE DATOS
    # Si se recibe 'full_name', se divide en FirstName y LastName para Salesforce.
    if 'full_name' in contact_data:
        full_name = contact_data.pop('full_name')
        parts = full_name.strip().split()
        contact_data.setdefault('FirstName', parts[0] if parts else "")
        contact_data.setdefault('LastName', " ".join(parts[1:]) if len(parts) > 1 else "")

    # El apellido es un campo requerido en Salesforce para los contactos.
    if not contact_data.get('LastName'):
        return jsonify({"status": "error", "message": "El campo 'LastName' es requerido (o un 'full_name' válido)."}), 400

    # Asegurar que el tipo de entidad está presente para la creación del contacto.
    contact_data.setdefault('Entity_Type__c', 'Individual')

    logging.info(f"Petición para crear contacto con datos: {contact_data}")
    try:
        # 2. CREACIÓN DEL CONTACTO
        # Se crea únicamente el contacto. El Flow en Salesforce se encargará de la cuenta.
        create_result = sf.Contact.create(contact_data)

        if create_result.get('success'):
            new_contact_id = create_result['id']
            logging.info(f"Contacto creado con ID: {new_contact_id}. Esperando para asociar cuenta vía Flow.")

            
            # 4. BÚSQUEDA DE LA CUENTA
            # Se intenta encontrar la cuenta que el Flow debería haber creado.
            # Por convención, el Flow nombra la cuenta usando el nombre completo en mayúsculas.
            account_name = f"{contact_data.get('FirstName', '')} {contact_data.get('LastName', '')}".strip().upper()
            safe_account_name = _escape_soql_str(account_name)
            
            account_id = None
            try:
                # Se construye y ejecuta la consulta SOQL para encontrar la cuenta.
                query = f"SELECT Id FROM Account WHERE Name = {safe_account_name} LIMIT 1"
                logging.info(f"Buscando cuenta con SOQL: {query}")
                account_result = sf.query(query)
                
                # 5. ASOCIACIÓN DE LA CUENTA
                if account_result.get('totalSize', 0) > 0:
                    account_id = account_result['records'][0]['Id']
                    logging.info(f"Cuenta encontrada con ID: {account_id}. Asociando con el contacto.")
                    # Se actualiza el campo 'AccountId' en el contacto para crear la relación.
                    sf.Contact.update(new_contact_id, {'AccountId': account_id})
                    logging.info(f"Contacto {new_contact_id} actualizado con AccountId {account_id}.")
                else:
                    # Si no se encuentra la cuenta, se registra una advertencia.
                    # El flujo no se detiene, el contacto queda creado pero sin cuenta asociada.
                    logging.warning(f"No se encontró una cuenta con el nombre '{account_name}' después de 5 segundos.")

            except Exception as e:
                # 6. MANEJO DE ERRORES DE ASOCIACIÓN
                # Si la búsqueda o actualización de la cuenta falla, no se interrumpe la respuesta exitosa
                # de la creación del contacto. Solo se registra el error para depuración.
                logging.error(f"Ocurrió un error al intentar asociar la cuenta con el contacto: {e}")

            # 7. RESPUESTA FINAL
            # Se prepara la respuesta JSON, incluyendo el AccountId si la asociación fue exitosa.
            new_contact_info = {"Id": new_contact_id, **contact_data}
            if account_id:
                new_contact_info['AccountId'] = account_id
            return jsonify({"status": "created", "contact": new_contact_info}), 201
        else:
            # Este bloque se ejecuta si la creación inicial del contacto falla.
            # Un error común aquí es 'CANNOT_EXECUTE_FLOW_TRIGGER' si el Flow tiene un problema.
            logging.error(f"Error de Salesforce al crear contacto: {create_result.get('errors')}")
            return jsonify({"status": "error", "message": "Error de Salesforce al crear el contacto.", "details": create_result.get('errors')}), 500

    except SalesforceGeneralError as e:
        logging.error(f"Error de Salesforce al crear: {e.code} - {e.content}")
        return jsonify({"status": "error", "message": "Error de Salesforce.", "details": e.content}), 500
    except Exception as e:
        logging.error(f"Error inesperado al crear: {e}")
        return jsonify({"status": "error", "message": "Ocurrió un error inesperado."}), 500

@app.route('/customer_service/create', methods=['POST'])
def create_customer_service_case():
    """
    Crea un nuevo registro de Customer_Service__c en Salesforce.
    Espera un JSON con los datos del sericio. Se requiere 'AccountId' y otros campos.

    """
    sf = get_salesforce_connection()
    data = request.json

    if not data:
        return jsonify({"status": "error", "message": "El cuerpo de la petición no puede estar vacío."}), 400
    
    #1. Validacion de Campos requeridos
    required_fields = [
        'AccountId', 
        'CallType__c',
        'ParentezcoDelCliente__c',
        'Fast_Note__c',
        'UltimoAnioDeAyuda__c',
        'Communication_channel__c',
        'TipoCliente__c',
        'TipoHumor_Cliente__c'
    ]

    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({"status": "error", "message": f"Faltan los siguientes campos requeridos: {', '.join(missing_fields)}"}), 400

    #2. Validacion de valores picklists
    picklists_validations = {
        'CallType__c': ['Inbone', 'Onbone'],
        'ParentezcoDelCliente__c': ['Cliente', 'Familiar del Cliente', 'Amigo del Cliente', 'Agencia de Gobierno', 'Un tercero', 'eje realtor...'],
        'UltimoAnioDeAyuda__c': ['2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017 o antes'],
        'Communication_channel__c': ['Text message', 'Phone', 'In person'],
        'TipoCliente__c': ['Cliente Actual', 'Cliente Retorno', 'Cliente Nuevo'],
        'TipoHumor_Cliente__c':[
            'Enojado', 'Frustrado', 'Desesperado', 'Calmado', 'Feliz', 'Apático', 'Celoso', 'Nublado', 'Preocupado',
            'Ansioso', 'Agradecido', 'Indeciso', 'Aliviado', 'Preparado', 'Impaciente', 'Inseguro', 'Interesado',
            'Resuelto', 'Curioso', 'Avergonzado', 'Resentido', 'Resignado', 'Optimista', 'Motivado'
        ]
    }

    for field, valid_values in picklists_validations.items():
        if data.get(field) not in valid_values:
            return jsonify({
                "status": "error", 
                "message": f"Valor invalido para el campo '{field}' ",
                "provided_value": data[field],
                "allowed_values": valid_values    
            }), 400

    # 3. Prepara el payload para Salesforce
    salesforce_payload = data.copy()
    #Mapeamos AccountId a Account__c para la relacion
    salesforce_payload['Account__c'] = salesforce_payload.pop('AccountId')

    logging.info(f"Petición para crear Customer_Service__c con datos: {salesforce_payload}")

    try: 
        # 4. Crear el registro en salesforce
        customer_service_object = getattr(sf, 'Customer_Service__c')
        create_result = customer_service_object.create(salesforce_payload)

        if create_result.get('success'):
            new_id = create_result['id']
            logging.info(f"Customer_Service__c creado con ID: {new_id}")

            response_data = {"Id": new_id, **data}
            return jsonify({"status": "created", "customer_service": response_data}), 201
        else:
            errors = create_result.get('errors', [])
            logging.error(f"Error de Salesforce al crear Customer_Service__c: {errors}")
            return jsonify({
                "status": "error",
                "message": "Error de Salesforce al crear el registro de servicio.",
                "details": errors
            }), 500
    except SalesforceGeneralError as e:
        logging.error(f"Error de Salesforce al crear Customer_Service__c: {e.code} - {e.content}")
        return jsonify({
            "status": "error", 
            "message": "Error de Salesforce.", 
            "details": e.content
        }), 500
    except Exception as e:
        logging.error(f"Error inesperado al crear Customer_Service__c: {e}")
        return jsonify({
            "status": "error", 
            "message": "Ocurrió un error inesperado."
        }), 500

@app.route('/contact/verify/dob', methods=['POST'])
def verify_contact_by_dob():
    """
    Verifica un contacto por nombre completo y fecha de nacimiento (DOB).
    Utiliza caché para mejorar el rendimiento en solicitudes repetidas.
    El campo de fecha de nacimiento en Salesforce debe tener el API Name 'DOB__c'.
    Espera un JSON: {"full_name": "Nombre Apellido", "dob": "YYYY-MM-DD"}
    """
    # Paso 1: Obtener la conexión a Salesforce y los datos de entrada.
    sf = get_salesforce_connection()
    data = request.json
    full_name = data.get('full_name')
    dob = data.get('dob')

    # Paso 2: Validar que los campos requeridos no estén vacíos.
    if not all([full_name, dob]):
        return jsonify({"status": "error", "message": "Los campos 'full_name' y 'dob' son requeridos."}), 400

    # Limpiar y normalizar el nombre completo.
    full_name = full_name.strip()

    try:
        # Paso 4: Validar el formato de la fecha de nacimiento.
        # SOQL requiere el formato YYYY-MM-DD para literales de fecha. Esta validación
        # previene errores de 'MALFORMED_QUERY' si el cliente envía un formato incorrecto.
        try:
            datetime.datetime.strptime(dob, '%Y-%m-%d')
        except ValueError:
            # No se cachea un error de formato de entrada, ya que es un error del cliente.
            return jsonify({"status": "error", "message": "El formato de 'dob' no es válido. Se esperaba YYYY-MM-DD."}), 400

        # Paso 5: Preparar los datos para la consulta SOQL, usando el campo 'Name'.
        safe_full_name = _escape_soql_str(full_name)
        # El literal de fecha se usa directamente, ya que SOQL no requiere comillas para este tipo de dato.
        safe_dob = dob  # dob ya está validado como YYYY-MM-DD

        # Paso 6: Construir y ejecutar la consulta SOQL.
        # Se usa el campo 'Name' que es un campo compuesto y generalmente indexado.
        query = (
            f"SELECT Id, FirstName, LastName, Email, DOB__c FROM Contact "
            f"WHERE Name = {safe_full_name} AND DOB__c = {safe_dob} LIMIT 1"
        )
        logging.info(f"Ejecutando SOQL de verificación: {query}")
        result = sf.query(query)

        # Paso 7: Procesar el resultado, guardarlo en caché y devolver la respuesta.
        if result.get('totalSize', 0) > 0:
            # Si se encuentra un registro, la verificación es exitosa.
            contact = result['records'][0]
            logging.info(f"Verificación exitosa para contacto: {contact['Id']}")
            response_data = {"status": "verified", "contact": contact}
            status_code = 200
        else:
            logging.info(f"Verificación fallida para '{full_name}' con DOB '{dob}'.")
            response_data = {"status": "not_verified", "message": "No se encontró un contacto que coincida con los datos proporcionados."}
            status_code = 404

        return jsonify(response_data), status_code

    # Paso 8: Manejo de excepciones.
    except SalesforceGeneralError as e:
        logging.error(f"Error de Salesforce durante la verificación: {e.code} - {e.content}")
        return jsonify({"status": "error", "message": "Error de Salesforce.", "details": e.content}), 500
    except Exception as e:
        logging.error(f"Error inesperado durante la verificación: {e}")
        return jsonify({"status": "error", "message": "Ocurrió un error inesperado."}), 500

@app.route('/contact/verify/dob-phone', methods=['POST'])
def verify_contact_by_phone():
    """
    Verifica un contacto por nombre completo, fecha de nacimiento (DOB) y teléfono.
    Usa el campo 'Name' para una búsqueda más eficiente y compara el teléfono
    ignorando caracteres de formato (espacios, guiones, etc.).
    Espera un JSON: {"full_name": "Nombre Apellido", "dob": "YYYY-MM-DD", "phone": "1234567890"}
    """
    # Paso 1: Obtener la conexión a Salesforce y los datos de entrada.
    sf = get_salesforce_connection()
    data = request.json
    full_name = data.get('full_name')
    dob = data.get('dob')
    phone = data.get('phone')

    # Paso 2: Validar que los campos requeridos no estén vacíos.
    if not all([full_name, dob, phone]):
        return jsonify({"status": "error", "message": "Los campos 'full_name', 'dob' y 'phone' son requeridos."}), 400

    # Limpiar y normalizar el nombre completo.
    full_name = full_name.strip()

    try:
        # Paso 3: Validar el formato de la fecha de nacimiento.
        try:
            datetime.datetime.strptime(dob, '%Y-%m-%d')
        except ValueError:
            return jsonify({"status": "error", "message": "El formato de 'dob' no es válido. Se esperaba YYYY-MM-DD."}), 400

        # Paso 4: Preparar los datos para la consulta SOQL.
        safe_full_name = _escape_soql_str(full_name)
        safe_dob = dob  # dob ya está validado como YYYY-MM-DD

        # Paso 5: Buscar contactos que coincidan con nombre y fecha de nacimiento.
        # Se usa el campo 'Name' que está indexado. El teléfono se recupera para ser
        # verificado en Python, permitiendo ignorar diferencias de formato.
        query = (
            f"SELECT Id, FirstName, LastName, Email, DOB__c, Phone FROM Contact "
            f"WHERE Name = {safe_full_name} AND DOB__c = {safe_dob}"
        )
        logging.info(f"Ejecutando SOQL de verificación (Nombre y DOB): {query}")
        result = sf.query(query)

        # Paso 6: Procesar el resultado y verificar el teléfono.
        if result.get('totalSize', 0) > 0:
            # Normalizar el número de teléfono de entrada (quitar caracteres no numéricos).
            input_phone_normalized = re.sub(r'\D', '', phone)

            # Iterar sobre los resultados y comparar los teléfonos normalizados.
            for contact in result['records']:
                sf_phone = contact.get('Phone')
                if sf_phone:
                    sf_phone_normalized = re.sub(r'\D', '', sf_phone)
                    if sf_phone_normalized == input_phone_normalized:
                        logging.info(f"Verificación exitosa para contacto: {contact['Id']}")
                        return jsonify({"status": "verified", "contact": contact}), 200
            
            # Si el bucle termina, se encontraron contactos por nombre/DOB pero el teléfono no coincidió.
            logging.warning(f"Verificación fallida para '{full_name}'. Se encontraron contactos por nombre/DOB pero el teléfono no coincidió.")
            return jsonify({"status": "not_verified", "message": "Los datos de nombre y fecha de nacimiento son correctos, pero el número de teléfono no coincide."}), 404
        else:
            # No se encontró ningún contacto que coincidiera con nombre y DOB.
            logging.info(f"Verificación fallida para '{full_name}'. No se encontró coincidencia por nombre y DOB.")
            return jsonify({"status": "not_verified", "message": "No se encontró un contacto que coincida con el nombre y la fecha de nacimiento proporcionados."}), 404
    
    # Paso 7: Manejo de excepciones.
    except SalesforceGeneralError as e:
        logging.error(f"Error de Salesforce durante la verificación: {e.code} - {e.content}")
        return jsonify({"status": "error", "message": "Error de Salesforce.", "details": e.content}), 500
    except Exception as e:
        logging.error(f"Error inesperado durante la verificación: {e}")
        return jsonify({"status": "error", "message": "Ocurrió un error inesperado."}), 500

@app.route('/script_case', methods=['POST'])
def create_script_case():
    """
    Crea un nuevo registro de Script_Case__c en Salesforce.
    Espera un JSON con los datos del caso. Se requiere 'ContactId' o 'AccountId'.
    Ej: {"ContactId": "003...", "X5_0_Estado_Civil__c": "Soltero", ...}
    """
    sf = get_salesforce_connection()
    case_data = request.json

    if not case_data:
        return jsonify({"status": "error", "message": "El cuerpo de la petición no puede estar vacío."}), 400

    # Extraer IDs de relación y eliminarlos del diccionario principal para evitar errores.
    contact_id = case_data.pop('ContactId', None)
    account_id = case_data.pop('AccountId', None)

    if not contact_id and not account_id:
        return jsonify({"status": "error", "message": "Se requiere 'ContactId' o 'AccountId' para relacionar el caso."}), 400

    # Preparar el payload para Salesforce. Los campos de relación usan el sufijo '__c'.
    salesforce_payload = case_data.copy()
    if contact_id:
        salesforce_payload['Contact__c'] = contact_id
    if account_id:
        salesforce_payload['Account__c'] = account_id

    logging.info(f"Petición para crear Script_Case__c con datos: {salesforce_payload}")
    try:
        # Usamos getattr para acceder al objeto dinámicamente por su nombre de API.
        script_case_object = getattr(sf, 'Script_Case__c')
        create_result = script_case_object.create(salesforce_payload)

        if create_result.get('success'):
            new_id = create_result['id']
            logging.info(f"Script_Case__c creado con ID: {new_id}")
            # Devolver el ID del nuevo registro junto con los datos enviados.
            new_case_info = {"Id": new_id, **case_data}
            if contact_id: new_case_info['ContactId'] = contact_id
            if account_id: new_case_info['AccountId'] = account_id
            
            return jsonify({"status": "created", "case": new_case_info}), 201
        else:
            errors = create_result.get('errors', [])
            logging.error(f"Error de Salesforce al crear Script_Case__c: {errors}")
            return jsonify({"status": "error", "message": "Error de Salesforce al crear el caso.", "details": errors}), 500

    except SalesforceGeneralError as e:
        logging.error(f"Error de Salesforce al crear Script_Case__c: {e.code} - {e.content}")
        return jsonify({"status": "error", "message": "Error de Salesforce.", "details": e.content}), 500
    except Exception as e:
        logging.error(f"Error inesperado al crear Script_Case__c: {e}")
        return jsonify({"status": "error", "message": "Ocurrió un error inesperado."}), 500


if __name__ == "__main__":
    # Este bloque es solo para desarrollo local.
    # En producción (Cloud Run), se usará un servidor WSGI como Gunicorn.
    # La conexión a Salesforce se establecerá de forma 'lazy' en la primera petición,
    # no durante el arranque.
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
