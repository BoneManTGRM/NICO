# Entorno de recopilación de proveedores

NICO trata el estado de recopilación del proveedor como evidencia, no como un detalle de implementación.

Una recopilación solo está lista cuando es de solo lectura, está vinculada a un repositorio, está vinculada a una revisión inmutable, está completa para todas las capacidades solicitadas y ha terminado toda la paginación. Los fallos de autenticación, las interrupciones del proveedor, los límites de solicitudes, la paginación incompleta y las capacidades faltantes permanecen como limitaciones explícitas y no pueden calificarse como evidencia satisfactoria.

Los modos admitidos son API, sondeo programado, eventos de webhook, transporte Git genérico y archivos de repositorio cargados. Git genérico y los archivos cargados ofrecen deliberadamente menos capacidades que las API completas de los proveedores.

Esta capa no almacena credenciales ni realiza solicitudes de red. Los clientes de cada proveedor deben convertir sus respuestas nativas a estos estados y conservar la identidad exacta del repositorio y de la revisión antes de que la evidencia entre en la puntuación o en los informes de evaluación.
