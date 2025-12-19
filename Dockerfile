# Usa una imagen base de Python oficial
FROM python:3.12-slim-bookworm

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de requerimientos e instálalos
COPY requirements.txt .
# COPY requirements-dev.txt . # Las dependencias de desarrollo no son necesarias para la imagen final

RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de la aplicación
# Excluye los directorios de git, tests, cache, etc.
COPY . .

# Expone el puerto en el que Flask se ejecutará
EXPOSE 5000

# Establece la variable de entorno FLASK_APP
ENV FLASK_APP=degiro_app.app
# Deshabilitar debug en producción
ENV FLASK_DEBUG=0 

# Comando para ejecutar la aplicación Flask
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
