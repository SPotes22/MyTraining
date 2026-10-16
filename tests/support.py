"""Utilidades compartidas por los tests.

Las contraseñas de prueba se generan en cada ejecución: ningún secreto literal en
el repositorio, ni siquiera de ejemplo (invariante I-13; GitGuardian marcó un
`set_password('...')` fijo en estos tests).
"""
import secrets

TEST_PASSWORD = secrets.token_urlsafe(12)    # contraseña válida de los usuarios de prueba
OTHER_PASSWORD = secrets.token_urlsafe(12)   # otra contraseña válida, distinta de la anterior
