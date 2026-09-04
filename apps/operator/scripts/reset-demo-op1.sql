-- Sólo entorno demo: vuelve a dejar "planned" la asignación de HOY de op1 para poder repetir el smoke.
UPDATE assignments SET status='planned'
WHERE operator_id=(SELECT id FROM users WHERE username='op1') AND shift_date=CURRENT_DATE;
