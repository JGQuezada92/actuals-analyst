import { spawn, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';
import { v4 as uuidv4 } from 'uuid';
import path from 'path';

export interface AgentResponse {
  id: string;
  type: 'progress' | 'analysis' | 'calculation' | 'chart' | 'error' | 'complete';
  data: any;
  timestamp: string;
}

export class AgentBridge extends EventEmitter {
  private pythonPath: string;
  private agentScriptPath: string;
  private agentDir: string;
  private activeProcess: ChildProcess | null = null;

  constructor(agentScriptPath: string, pythonPath: string = 'python') {
    super();
    this.agentScriptPath = agentScriptPath;
    this.pythonPath = pythonPath;
    this.agentDir = path.dirname(agentScriptPath);
  }

  isHealthy(): boolean {
    return true;
  }

  async analyzeQuery(
    query: string,
    options: { includeCharts?: boolean; maxIterations?: number } = {},
    onProgress?: (response: AgentResponse) => void
  ): Promise<any> {
    const requestId = uuidv4();
    
    return new Promise((resolve, reject) => {
      // Build command arguments (script path is NOT included here - it goes in spawn)
      const cmdArgs = ['analyze', query];

      if (!options.includeCharts) {
        cmdArgs.push('--no-charts');
      }

      if (options.maxIterations) {
        cmdArgs.push('--iterations', options.maxIterations.toString());
      }

      // On Windows, use cmd.exe to handle "py -3.13" command
      const isWindows = process.platform === 'win32';
      let proc: ChildProcess;
      
      // Set environment variable to request JSON output
      const env = { ...process.env, JSON_OUTPUT: 'true' };
      
      if (isWindows && this.pythonPath.includes(' ')) {
        // For Windows with "py -3.13", use the Python launcher directly
        // Split the Python command and pass arguments as array to spawn
        const pythonCmd = this.pythonPath.split(' ');
        const pythonExec = pythonCmd[0]; // "py"
        const pythonVersion = pythonCmd[1]; // "-3.13"
        
        // Build arguments array: [version, script_path, ...command_args]
        const spawnArgs: string[] = [pythonVersion, this.agentScriptPath, ...cmdArgs];
        
        console.log(`🐍 Running (Windows): ${pythonExec} ${spawnArgs.join(' ')}`);
        proc = spawn(pythonExec, spawnArgs, {
          cwd: this.agentDir,
          env: env,
          shell: false, // Don't use shell - spawn handles paths with spaces automatically
        });
      } else {
        // Split Python path if it contains arguments
        const pythonCmd = this.pythonPath.split(' ');
        const pythonExec = pythonCmd[0];
        const pythonArgs = pythonCmd.slice(1);
        const allArgs = [...pythonArgs, this.agentScriptPath, ...cmdArgs];
        console.log(`🐍 Running: ${pythonExec} ${allArgs.join(' ')}`);
        proc = spawn(pythonExec, allArgs, {
          cwd: this.agentDir,
          env: env,
          shell: isWindows,
        });
      }

      this.activeProcess = proc;
      let stdout = '';
      let stderr = '';

      console.log(`[Agent] Starting Python process for query: "${query.substring(0, 50)}..."`);

      proc.stdout.on('data', (data: Buffer) => {
        const chunk = data.toString();
        stdout += chunk;
        // Log ALL stdout output for debugging
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.trim()) {
            console.log(`[Agent stdout] ${line}`);
          }
        }
        this.parseStreamingOutput(chunk, requestId, onProgress);
      });

      proc.stderr.on('data', (data: Buffer) => {
        const chunk = data.toString();
        stderr += chunk;
        // Log ALL stderr output for debugging
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.trim()) {
            console.log(`[Agent stderr] ${line}`);
          }
        }
        this.parseProgressOutput(chunk, requestId, onProgress);
      });

      proc.on('close', (code) => {
        this.activeProcess = null;

        console.log(`[Agent] Process exited with code ${code}`);
        
        if (code === 0) {
          try {
            const result = this.extractFinalResult(stdout);
            console.log(`[Agent] Successfully parsed result`);
            resolve(result);
          } catch (e) {
            console.warn(`[Agent] Failed to parse JSON result, returning raw output:`, e);
            resolve({ analysis: stdout, raw: true });
          }
        } else {
          const errorMessage = `Agent exited with code ${code}`;
          const errorDetails = stderr.slice(-1000); // Last 1000 chars of stderr
          console.error(`[Agent Error] ${errorMessage}`);
          console.error(`[Agent Error Details] ${errorDetails}`);
          
          // Try to extract meaningful error from stderr
          const errorLines = stderr.split('\n').filter(line => 
            line.includes('Error') || 
            line.includes('Exception') || 
            line.includes('Traceback') ||
            line.includes('File') ||
            line.trim().length > 0
          );
          
          const meaningfulError = errorLines.slice(-10).join('\n') || errorDetails;
          reject(new Error(`${errorMessage}\n\n${meaningfulError}`));
        }
      });

      proc.on('error', (error) => {
        this.activeProcess = null;
        console.error(`[Agent Process Error]`, error);
        reject(new Error(`Failed to start Python process: ${error.message}`));
      });
    });
  }

  private parseStreamingOutput(
    chunk: string, 
    requestId: string, 
    onProgress?: (response: AgentResponse) => void
  ) {
    const lines = chunk.split('\n').filter(l => l.trim());
    
    for (const line of lines) {
      try {
        if (line.startsWith('{') && line.endsWith('}')) {
          const data = JSON.parse(line);
          if (onProgress) {
            onProgress({
              id: requestId,
              type: data.type || 'progress',
              data,
              timestamp: new Date().toISOString(),
            });
          }
        }
      } catch {
        // Not JSON, ignore
      }
    }
  }

  private parseProgressOutput(
    chunk: string,
    requestId: string,
    onProgress?: (response: AgentResponse) => void
  ) {
    const phaseMatch = chunk.match(/Phase (\d+):\s*(.+)/i);
    if (phaseMatch && onProgress) {
      onProgress({
        id: requestId,
        type: 'progress',
        data: {
          phase: parseInt(phaseMatch[1]),
          message: phaseMatch[2].trim(),
        },
        timestamp: new Date().toISOString(),
      });
    }
  }

  private extractFinalResult(stdout: string): any {
    // Look for JSON in markdown code block
    const jsonMatch = stdout.match(/```json\n([\s\S]*?)\n```/);
    if (jsonMatch) {
      return JSON.parse(jsonMatch[1]);
    }

    // Look for standalone JSON at end
    const lines = stdout.trim().split('\n');
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();
      if (line.startsWith('{') && line.endsWith('}')) {
        try {
          return JSON.parse(line);
        } catch {
          continue;
        }
      }
    }

    throw new Error('No JSON result found');
  }

  async getConfiguration(): Promise<any> {
    return new Promise((resolve, reject) => {
      const isWindows = process.platform === 'win32';
      let proc: ChildProcess;
      
      if (isWindows && this.pythonPath.includes(' ')) {
        const pythonCmd = this.pythonPath.split(' ');
        const pythonExec = pythonCmd[0];
        const pythonVersion = pythonCmd[1];
        proc = spawn(pythonExec, [pythonVersion, this.agentScriptPath, 'setup'], {
          cwd: this.agentDir,
          env: { ...process.env },
          shell: false,
        });
      } else {
        const pythonCmd = this.pythonPath.split(' ');
        const pythonExec = pythonCmd[0];
        const pythonArgs = pythonCmd.slice(1);
        const allArgs = [...pythonArgs, this.agentScriptPath, 'setup'];
        proc = spawn(pythonExec, allArgs, {
          cwd: this.agentDir,
          env: { ...process.env },
          shell: isWindows,
        });
      }

      let stdout = '';
      proc.stdout.on('data', (data) => { stdout += data.toString(); });
      proc.on('close', (code) => {
        if (code === 0) {
          resolve(this.parseSetupOutput(stdout));
        } else {
          reject(new Error('Failed to get configuration'));
        }
      });
    });
  }

  private parseSetupOutput(output: string): any {
    const config: any = { model: {}, netsuite: {}, slack: {}, fiscal: {} };

    const modelMatch = output.match(/\[Model\] Active Model: (.+)/);
    if (modelMatch) config.model.active = modelMatch[1].trim();

    const providerMatch = output.match(/Provider: (.+)/);
    if (providerMatch) config.model.provider = providerMatch[1].trim();

    const apiKeyMatch = output.match(/\[(OK|MISSING)\] API Key/);
    if (apiKeyMatch) config.model.hasApiKey = apiKeyMatch[1] === 'OK';

    return config;
  }

  async getRegistryStats(): Promise<any> {
    return new Promise((resolve, reject) => {
      const isWindows = process.platform === 'win32';
      let proc: ChildProcess;
      
      if (isWindows && this.pythonPath.includes(' ')) {
        const pythonCmd = this.pythonPath.split(' ');
        const pythonExec = pythonCmd[0];
        const pythonVersion = pythonCmd[1];
        proc = spawn(pythonExec, [pythonVersion, this.agentScriptPath, 'registry-stats'], {
          cwd: this.agentDir,
          env: { ...process.env },
          shell: false,
        });
      } else {
        const pythonCmd = this.pythonPath.split(' ');
        const pythonExec = pythonCmd[0];
        const pythonArgs = pythonCmd.slice(1);
        const allArgs = [...pythonArgs, this.agentScriptPath, 'registry-stats'];
        proc = spawn(pythonExec, allArgs, {
          cwd: this.agentDir,
          env: { ...process.env },
          shell: isWindows,
        });
      }

      let stdout = '';
      proc.stdout.on('data', (data) => { stdout += data.toString(); });
      proc.on('close', (code) => {
        if (code === 0) {
          resolve(this.parseRegistryStats(stdout));
        } else {
          reject(new Error('Failed to get registry stats'));
        }
      });
    });
  }

  private parseRegistryStats(output: string): any {
    const stats: any = {};
    
    const patterns = [
      { key: 'departments', pattern: /Departments:\s*([\d,]+)/ },
      { key: 'accounts', pattern: /Accounts:\s*([\d,]+)/ },
      { key: 'accountNumbers', pattern: /Account Numbers:\s*([\d,]+)/ },
      { key: 'subsidiaries', pattern: /Subsidiaries:\s*([\d,]+)/ },
      { key: 'transactionTypes', pattern: /Transaction Types:\s*([\d,]+)/ },
      { key: 'indexTerms', pattern: /Index Terms:\s*([\d,]+)/ },
      { key: 'sourceRows', pattern: /Source Rows:\s*([\d,]+)/ },
      { key: 'builtAt', pattern: /Built At:\s*(.+)/ },
      { key: 'cacheValid', pattern: /Cache Valid:\s*(.+)/ },
    ];

    for (const { key, pattern } of patterns) {
      const match = output.match(pattern);
      if (match) {
        const val = match[1].trim().replace(/,/g, '');
        stats[key] = key === 'builtAt' || key === 'cacheValid' ? match[1].trim() : parseInt(val);
      }
    }

    return stats;
  }

  async refreshRegistry(onProgress?: (message: string) => void): Promise<void> {
    return new Promise((resolve, reject) => {
      const isWindows = process.platform === 'win32';
      let proc: ChildProcess;
      
      if (isWindows && this.pythonPath.includes(' ')) {
        const pythonCmd = this.pythonPath.split(' ');
        const pythonExec = pythonCmd[0];
        const pythonVersion = pythonCmd[1];
        proc = spawn(pythonExec, [pythonVersion, this.agentScriptPath, 'refresh-registry'], {
          cwd: this.agentDir,
          env: { ...process.env },
          shell: false,
        });
      } else {
        const pythonCmd = this.pythonPath.split(' ');
        const pythonExec = pythonCmd[0];
        const pythonArgs = pythonCmd.slice(1);
        const allArgs = [...pythonArgs, this.agentScriptPath, 'refresh-registry'];
        proc = spawn(pythonExec, allArgs, {
          cwd: this.agentDir,
          env: { ...process.env },
          shell: isWindows,
        });
      }

      proc.stderr.on('data', (data) => {
        if (onProgress) onProgress(data.toString());
      });

      proc.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error('Failed to refresh registry'));
      });
    });
  }

  shutdown() {
    if (this.activeProcess) {
      this.activeProcess.kill('SIGTERM');
    }
  }
}

