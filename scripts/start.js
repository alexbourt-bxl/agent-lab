/**
 * Start backend and frontend in parallel. Run from project root.
 * No extra dependencies - uses Node built-in child_process.
 */
const { spawn } = require('child_process');
const path = require('path');

const root = path.join(__dirname, '..');

const backend = spawn('python', ['main.py'], {
  cwd: path.join(root, 'backend'),
  stdio: 'inherit',
  shell: true,
});

const frontend = spawn('npm', ['run', 'dev'], {
  cwd: path.join(root, 'frontend'),
  stdio: 'inherit',
  shell: true,
});

function killAll()
{
  backend.kill();
  frontend.kill();
  process.exit();
}

process.on('SIGINT', killAll);
process.on('SIGTERM', killAll);

backend.on('error', (err) =>
{
  console.error('Backend failed to start:', err.message);
  killAll();
});

frontend.on('error', (err) =>
{
  console.error('Frontend failed to start:', err.message);
  killAll();
});
