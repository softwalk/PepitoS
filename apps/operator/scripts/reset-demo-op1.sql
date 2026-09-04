-- Sólo entorno demo: vuelve a dejar "planned" la asignación de HOY (hora de México, como la API) de op1
-- para poder repetir el smoke.
UPDATE assignments SET status='planned'
WHERE operator_id=(SELECT id FROM users WHERE username='op1')
  AND shift_date=(now() AT TIME ZONE 'America/Mexico_City')::date;
