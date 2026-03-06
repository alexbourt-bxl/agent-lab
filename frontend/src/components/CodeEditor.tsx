import Editor from '@monaco-editor/react';
import styles from './CodeEditor.module.css';

type CodeEditorProps =
{
  code: string;
  onCodeChange: (value: string) => void;
};

function CodeEditor(
{
  code,
  onCodeChange,
}: CodeEditorProps)
{
  return (
    <div className={styles.panelBody}>
      <div className={styles.editorShell}>
        <Editor
          defaultLanguage="python"
          language="python"
          theme="vs-dark"
          value={code}
          onChange={(value) => onCodeChange(value ?? '')}
          options={
          {
            minimap:
            {
              enabled: false,
            },
            fontSize: 14,
            padding:
            {
              top: 16,
            },
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    </div>
  );
}

export default CodeEditor;
