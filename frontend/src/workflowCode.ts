/**
 * Shared workflow/agent code parsing and manipulation.
 * Single source of truth for agent config extraction, code merging, and default code.
 */

const DEFAULT_MAX_ROUNDS = 8;

export type AgentConfig =
{
  name: string;
  className: string;
  variable: string;
};

export function findMatchingParen(str: string, openIndex: number): number
{
  let depth = 1;
  for (let i = openIndex + 1; i < str.length; i++)
  {
    if (str[i] === '(')
    {
      depth++;
    }
    else if (str[i] === ')')
    {
      depth--;
      if (depth === 0)
      {
        return i;
      }
    }
  }
  return str.length;
}

export function parseAgentConfigsFromCode(code: string): AgentConfig[]
{
  const configs: AgentConfig[] = [];
  const classMatches = [...code.matchAll(/class (\w+)\(Agent\):\s*/g)];
  const classesByName = new Map<string, { name: string }>();

  for (let i = 0; i < classMatches.length; i++)
  {
    const className = classMatches[i][1];
    const bodyStart = classMatches[i].index! + classMatches[i][0].length;
    const bodyEnd = i + 1 < classMatches.length
      ? classMatches[i + 1].index!
      : code.length;
    const nextClass = code.slice(bodyStart).match(/\nclass \w+\(Agent\)/);
    const end = nextClass
      ? bodyStart + nextClass.index!
      : bodyEnd;
    const body = code.slice(bodyStart, end);
    const nameMatch = body.match(/name\s*=\s*["']([^"']*)["']/);
    classesByName.set(className, {
      name: nameMatch ? nameMatch[1].trim() : className,
    });
  }

  for (const [className, attrs] of classesByName)
  {
    let variable = '';
    const pattern = new RegExp(
      `(\\w+)\\s*=\\s*${className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\(`,
      'g',
    );
    let m;
    while ((m = pattern.exec(code)) !== null)
    {
      const argsStart = m.index + m[0].length;
      const argsEnd = findMatchingParen(code, argsStart - 1);
      const argumentsStr = code.slice(argsStart, argsEnd);
      const goalMatch = argumentsStr.match(/goal\s*=\s*["']([^"']*)["']/);
      if (goalMatch)
      {
        variable = m[1];
        break;
      }
    }
    configs.push({
      name: attrs.name || className,
      className,
      variable: variable || className.charAt(0).toLowerCase() + className.slice(1),
    });
  }

  configs.sort((a, b) =>
  {
    const instA = code.indexOf(`${a.variable} = ${a.className}`);
    const instB = code.indexOf(`${b.variable} = ${b.className}`);
    const idxA = instA >= 0 ? instA : code.indexOf(`class ${a.className}(Agent)`);
    const idxB = instB >= 0 ? instB : code.indexOf(`class ${b.className}(Agent)`);
    return idxA - idxB;
  });
  return configs;
}

export function getAgentDisplayNameFromFileContent(content: string): string
{
  const nameMatch = content.match(/name\s*=\s*["']([^"']*)["']/);
  if (nameMatch && nameMatch[1].trim())
  {
    return nameMatch[1].trim();
  }
  const classMatch = content.match(/class (\w+)\(Agent\)/);
  return classMatch ? classMatch[1] : '';
}

export function agentNameToKebab(name: string): string
{
  const result: string[] = [];
  for (let i = 0; i < name.length; i++)
  {
    const c = name[i];
    if (/\s/.test(c))
    {
      if (result.length > 0 && result[result.length - 1] !== '-')
      {
        result.push('-');
      }
    }
    else if (/[A-Z]/.test(c) && i > 0 && result.length > 0 && result[result.length - 1] !== '-')
    {
      result.push('-');
      result.push(c.toLowerCase());
    }
    else if (/[a-zA-Z0-9]/.test(c))
    {
      result.push(c.toLowerCase());
    }
  }
  return result.join('').replace(/--/g, '-').replace(/^-+|-+$/g, '') || 'agent';
}

export function removeAgentFromCode(code: string, agentName: string): string | null
{
  const configs = parseAgentConfigsFromCode(code);
  const config = configs.find((c) => c.name === agentName);
  if (!config)
  {
    return null;
  }

  const escapedClass = config.className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const escapedVar = config.variable.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  let result = code;

  const classRegex = new RegExp(
    `class ${escapedClass}\\(Agent\\):\\s*\\n(?:    .+\\n)*`,
    'g',
  );
  result = result.replace(classRegex, '');

  const instanceRegex = new RegExp(
    `${escapedVar}\\s*=\\s*${escapedClass}\\s*\\([^)]*\\)\\s*\\n?`,
    'g',
  );
  result = result.replace(instanceRegex, '');

  return result.replace(/\n{3,}/g, '\n\n').trim();
}

export type AgentCodeConfig =
{
  className: string;
  displayName: string;
  role: string;
  tools?: string;
  variableName: string;
  task: string;
  input: string;
  maxRounds?: number;
};

export function createAgentCode(config: AgentCodeConfig): { classDef: string; instantiation: string }
{
  const toolsLine = config.tools != null && config.tools !== '[]'
    ? `    tools = ${config.tools}\n`
    : '';
  const maxRoundsLine = config.maxRounds != null && config.maxRounds !== DEFAULT_MAX_ROUNDS
    ? `    max_rounds = ${config.maxRounds}\n`
    : '';
  const classDef = `
class ${config.className}(Agent):
    name = "${config.displayName}"
    role = "${config.role}"
${toolsLine}${maxRoundsLine}`;
  const instantiation = `${config.variableName} = ${config.className}(\n    task="${config.task}",\n    input=${config.input}\n)`;
  return { classDef, instantiation };
}

export function addAgentSkeletonToCode(code: string): { code: string; newAgentName: string }
{
  const configs = parseAgentConfigsFromCode(code);
  const newAgentNums = configs
    .map((c) =>
    {
      if (c.name === 'New Agent')
      {
        return 1;
      }
      const m = c.name.match(/^New Agent (\d+)$/);
      return m ? Number(m[1]) : 0;
    })
    .filter((n) => n > 0);
  const nextNum = newAgentNums.length > 0 ? Math.max(...newAgentNums) + 1 : 1;
  const displayName = nextNum === 1 ? 'New Agent' : `New Agent ${nextNum}`;
  const className = `NewAgent${nextNum}`;
  const variableName = nextNum === 1 ? 'newAgent' : `newAgent${nextNum}`;
  const { classDef, instantiation } = createAgentCode(
  {
    className,
    displayName,
    role: '',
    variableName,
    task: '...',
    input: '...',
  });

  if (configs.length === 0)
  {
    return {
      code: code.trimEnd() + classDef + '\n\n' + instantiation + '\n',
      newAgentName: displayName,
    };
  }

  const firstIdx = code.indexOf(`${configs[0].variable} = ${configs[0].className}`);
  if (firstIdx < 0)
  {
    return {
      code: code.trimEnd() + classDef + '\n\n' + instantiation + '\n',
      newAgentName: displayName,
    };
  }

  const beforeInstantiations = code.slice(0, firstIdx).trimEnd();
  const instantiations = code.slice(firstIdx).trimStart();

  const withNewClass = beforeInstantiations + classDef + '\n\n' + instantiations;
  return {
    code: withNewClass.trimEnd() + '\n\n' + instantiation + '\n',
    newAgentName: displayName,
  };
}

export function buildDefaultCode(): string
{
  const researcher = createAgentCode(
  {
    className: 'Researcher',
    displayName: 'Researcher',
    role: 'Market researcher specializing in SaaS and B2B trends.',
    tools: '[WebSearch]',
    variableName: 'researcher',
    task: "Find and refine a promising SaaS idea based on analyst feedback",
    input: 'analyst.output',
  });
  const analyst = createAgentCode(
  {
    className: 'Analyst',
    displayName: 'Analyst',
    role: "Critical analyst who identifies flaws and improvement opportunities.",
    variableName: 'analyst',
    task: "Review the researcher's latest SaaS idea and only mark done when the idea is strong enough",
    input: 'researcher.output',
  });
  return (
    researcher.classDef.trim() +
    '\n\n' +
    analyst.classDef.trim() +
    '\n\n' +
    researcher.instantiation +
    '\n\n' +
    analyst.instantiation +
    '\n'
  );
}

export const DEFAULT_CODE = buildDefaultCode();

export function getTabLabel(config: { name: string; className: string }): string
{
  const trimmed = config.name.trim();
  return trimmed || config.className || 'Agent?';
}

export function extractWorkflowCode(code: string): string
{
  const firstInst = code.match(/\n([A-Za-z_]\w*)\s*=\s*\w+\s*\(/);
  if (firstInst && firstInst.index !== undefined)
  {
    return code.slice(firstInst.index).trimStart();
  }
  return '';
}

export function extractAgentClassCode(code: string, className: string): string
{
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = code.match(
    new RegExp(
      `(class ${escaped}\\(Agent\\):[\\s\\S]*?)(?=\\nclass \\w+\\(Agent\\)|\\n[A-Za-z_]\\w*\\s*=|$)`,
    ),
  );
  return match ? match[1].trimEnd() : '';
}

export function mergeWorkflowCodeIntoFullCode(fullCode: string, workflowCode: string): string
{
  const firstInst = fullCode.match(/\n([A-Za-z_]\w*)\s*=\s*\w+\s*\(/);
  if (!firstInst || firstInst.index === undefined)
  {
    return fullCode.trimEnd() + (fullCode.endsWith('\n') ? '' : '\n') + workflowCode + '\n';
  }
  const workflowStart = firstInst.index;
  const before = fullCode.slice(0, workflowStart);
  const trailing = fullCode.slice(workflowStart).match(/^\s*/)?.[0] ?? '';
  return before + trailing + workflowCode;
}

export function mergeAgentClassCodeIntoFullCode(
  fullCode: string,
  className: string,
  agentCode: string,
): string
{
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(
    `(class ${escaped}\\(Agent\\):[\\s\\S]*?)(?=\\nclass \\w+\\(Agent\\)|\\n[A-Za-z_]\\w*\\s*=|$)`,
  );
  const match = fullCode.match(pattern);
  if (!match)
  {
    return fullCode;
  }
  return fullCode.replace(pattern, agentCode);
}

// --- Workflow JSON serialization ---

export type WorkflowAgentJson =
{
  className: string;
  name: string;
  role: string;
  tools?: string[];
  maxRounds?: number;
};

export type WorkflowInstantiationJson =
{
  variable: string;
  className: string;
  task: string;
  inputSourceVariable?: string;
};

export type WorkflowJson =
{
  version: number;
  agents: WorkflowAgentJson[];
  instantiations: WorkflowInstantiationJson[];
};

function extractRoleToolsMaxRoundsFromClassBody(body: string): {
  role: string;
  tools: string[];
  maxRounds: number;
  toolsInSource: boolean;
  maxRoundsInSource: boolean;
}
{
  const roleMatch = body.match(/role\s*=\s*["']([^"']*)["']/);
  const toolsMatch = body.match(/tools\s*=\s*\[([^\]]*)\]/);
  const maxRoundsMatch = body.match(/max_rounds\s*=\s*(\d+)/);
  const tools: string[] = [];
  if (toolsMatch && toolsMatch[1].trim())
  {
    tools.push(...toolsMatch[1].split(',').map((t) => t.trim()).filter(Boolean));
  }
  return {
    role: roleMatch ? roleMatch[1] : '',
    tools,
    maxRounds: maxRoundsMatch ? parseInt(maxRoundsMatch[1], 10) : DEFAULT_MAX_ROUNDS,
    toolsInSource: toolsMatch !== null,
    maxRoundsInSource: maxRoundsMatch !== null,
  };
}

function extractTaskAndInputFromInstantiation(code: string, className: string, variable: string): { task: string; inputSourceVariable?: string }
{
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(
    `${variable}\\s*=\\s*${escaped}\\s*\\(([^)]*)\\)`,
    's',
  );
  const m = code.match(pattern);
  if (!m)
  {
    return { task: '' };
  }
  const args = m[1];
  const taskMatch = args.match(/task\s*=\s*["']([^"']*)["']/) || args.match(/goal\s*=\s*["']([^"']*)["']/);
  const inputMatch = args.match(/input\s*=\s*(\w+)\.output/);
  return {
    task: taskMatch ? taskMatch[1] : '',
    inputSourceVariable: inputMatch ? inputMatch[1] : undefined,
  };
}

export function serializeWorkflowToJson(code: string): WorkflowJson
{
  const configs = parseAgentConfigsFromCode(code);
  const agents: WorkflowAgentJson[] = [];
  const instantiations: WorkflowInstantiationJson[] = [];

  for (const config of configs)
  {
    const classBody = extractAgentClassCode(code, config.className);
    const { role, tools, maxRounds, toolsInSource, maxRoundsInSource } =
      extractRoleToolsMaxRoundsFromClassBody(classBody);
    const { task, inputSourceVariable } = extractTaskAndInputFromInstantiation(code, config.className, config.variable);

    const agent: WorkflowAgentJson = {
      className: config.className,
      name: config.name,
      role,
    };
    if (toolsInSource)
    {
      agent.tools = tools;
    }
    if (maxRoundsInSource)
    {
      agent.maxRounds = maxRounds;
    }
    agents.push(agent);
    instantiations.push({
      variable: config.variable,
      className: config.className,
      task,
      inputSourceVariable,
    });
  }

  return {
    version: 1,
    agents,
    instantiations,
  };
}

export function deserializeWorkflowFromJson(json: WorkflowJson): string
{
  const classParts: string[] = [];
  const instParts: string[] = [];

  for (const agent of json.agents)
  {
    const inst = json.instantiations.find((x) => x.className === agent.className);
    if (!inst)
    {
      continue;
    }
    const toolsLine = agent.tools != null && agent.tools.length > 0
      ? `    tools = [${agent.tools.join(', ')}]\n`
      : '';
    const maxRoundsLine = agent.maxRounds != null && agent.maxRounds !== DEFAULT_MAX_ROUNDS
      ? `    max_rounds = ${agent.maxRounds}\n`
      : '';
    const classDef = `
class ${agent.className}(Agent):
    name = "${agent.name}"
    role = "${agent.role}"
${toolsLine}${maxRoundsLine}`;
    const inputArg = inst.inputSourceVariable ? `${inst.inputSourceVariable}.output` : 'None';
    const instantiation = `${inst.variable} = ${agent.className}(\n    task="${inst.task}",\n    input=${inputArg}\n)`;
    classParts.push(classDef.trim());
    instParts.push(instantiation);
  }

  return classParts.join('\n\n') + '\n\n' + instParts.join('\n\n') + '\n';
}

export function getEffectiveMaxRounds(code: string): number
{
  const configs = parseAgentConfigsFromCode(code);
  if (configs.length === 0)
  {
    return DEFAULT_MAX_ROUNDS;
  }
  let max = DEFAULT_MAX_ROUNDS;
  for (const config of configs)
  {
    const classBody = extractAgentClassCode(code, config.className);
    const { maxRounds } = extractRoleToolsMaxRoundsFromClassBody(classBody);
    if (maxRounds > max)
    {
      max = maxRounds;
    }
  }
  return max;
}
