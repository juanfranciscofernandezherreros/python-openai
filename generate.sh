#!/bin/bash

# Crear carpeta de salida si no existe
mkdir -p output_sierra_madrid

echo "🌲 Iniciando generación de artículos sobre la Sierra de Madrid..."

# Artículo 1: Pueblos con encanto
python3 generateArticle.py \
  --tag "Sierra de Madrid" \
  --category "Turismo" \
  --subcategory "Pueblos" \
  --title "Los pueblos más bonitos de la Sierra de Madrid: historia y encanto" \
  --output "output_sierra_madrid/pueblos-sierra-$(date +%Y-%m-%d_%H-%M-%S).json"

echo "⏳ Esperando 10 segundos para evitar límites de API..."
sleep 10

# Artículo 2: Naturaleza y Deporte
python3 generateArticle.py \
  --tag "Guadarrama" \
  --category "Turismo" \
  --subcategory "Naturaleza" \
  --title "Rutas por el Parque Nacional de la Sierra de Guadarrama: de Peñalara a La Pedriza" \
  --output "output_sierra_madrid/rutas-guadarrama-$(date +%Y-%m-%d_%H-%M-%S).json"

echo "⏳ Esperando 10 segundos..."
sleep 10

# Artículo 3: Gastronomía y Ocio
python3 generateArticle.py \
  --tag "Gastronomía Madrid" \
  --category "Turismo" \
  --subcategory "Gastronomía" \
  --title "Qué comer en la Sierra de Madrid: del asado de cordero a los judiones" \
  --output "output_sierra_madrid/gastronomia-sierra-$(date +%Y-%m-%d_%H-%M-%S).json"

echo "✅ Proceso finalizado. Artículos guardados en 'output_sierra_madrid'."