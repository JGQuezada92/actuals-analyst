import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';

export class ConfigStore {
  private configDir: string;

  constructor(configDir: string) {
    this.configDir = configDir;
  }

  async listPrompts(): Promise<Array<{ name: string; versions: string[] }>> {
    const promptsDir = path.join(this.configDir, 'prompts');
    
    if (!fs.existsSync(promptsDir)) {
      return [];
    }

    const result: Array<{ name: string; versions: string[] }> = [];

    for (const dir of fs.readdirSync(promptsDir)) {
      const promptDir = path.join(promptsDir, dir);
      if (fs.statSync(promptDir).isDirectory()) {
        const versions = fs.readdirSync(promptDir)
          .filter(f => f.startsWith('v') && f.endsWith('.yaml'))
          .map(f => f.replace('.yaml', '').substring(1));
        
        result.push({ name: dir, versions });
      }
    }

    return result;
  }

  async getPrompt(name: string, version?: string): Promise<any> {
    const promptsDir = path.join(this.configDir, 'prompts', name);
    
    if (!fs.existsSync(promptsDir)) {
      throw new Error(`Prompt not found: ${name}`);
    }

    let versionToLoad = version;
    if (!versionToLoad) {
      const versions = fs.readdirSync(promptsDir)
        .filter(f => f.startsWith('v') && f.endsWith('.yaml'))
        .map(f => f.replace('.yaml', '').substring(1))
        .sort((a, b) => {
          const aParts = a.split('.').map(Number);
          const bParts = b.split('.').map(Number);
          for (let i = 0; i < Math.max(aParts.length, bParts.length); i++) {
            if ((aParts[i] || 0) !== (bParts[i] || 0)) {
              return (bParts[i] || 0) - (aParts[i] || 0);
            }
          }
          return 0;
        });
      versionToLoad = versions[0];
    }

    const filePath = path.join(promptsDir, `v${versionToLoad}.yaml`);
    if (!fs.existsSync(filePath)) {
      throw new Error(`Prompt version not found: ${name} v${versionToLoad}`);
    }

    const content = fs.readFileSync(filePath, 'utf-8');
    return yaml.load(content);
  }
}

