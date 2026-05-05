const { OpenAI } = require('openai');
const { DeepSeek } = require('deepseek');
const fs = require('fs');

class LLMClient {
  constructor() {
    this.openai = null;
    this.deepseek = null;
    this.commandDescriptions = null;
    this.loadCommandDescriptions();
  }

  loadCommandDescriptions() {
    try {
      const data = fs.readFileSync('ai_command_descriptions.json', 'utf8');
      this.commandDescriptions = JSON.parse(data);
    } catch (error) {
      console.error('Error loading command descriptions:', error);
      this.commandDescriptions = null;
    }
  }

  initialize(apiKey, provider = 'openai') {
    if (provider === 'openai') {
      this.openai = new OpenAI({ apiKey });
    } else if (provider === 'deepseek') {
      this.deepseek = new DeepSeek({ apiKey });
    }
  }

  getSystemPrompt() {
    let systemPrompt = `
You are a CAD assistant that helps users interact with a 3D model viewer. 
You can execute commands to control the viewer, load models, and analyze geometry.

Available commands:`;

    if (this.commandDescriptions && this.commandDescriptions.AICommandManager && this.commandDescriptions.AICommandManager.functions) {
      const functions = this.commandDescriptions.AICommandManager.functions;
      Object.keys(functions).forEach((funcName, index) => {
        const func = functions[funcName];
        systemPrompt += `\n${index + 1}. ${funcName}(${Object.keys(func.parameters || {}).join(', ')}) - ${func.description}`;
        systemPrompt += `\n   调用时机: ${func.call_when}`;
        if (func.examples && func.examples.length > 0) {
          systemPrompt += `\n   示例: ${func.examples.join(', ')}`;
        }
      });
    } else {
      // Fallback to basic commands
      systemPrompt += `
1. loadModel(filename) - Load a 3D model file
2. resetCamera() - Reset camera to default position
3. setCameraPosition(x, y, z) - Set camera position
4. setCameraRotation(pitch, yaw) - Set camera rotation
5. setZoom(zoom) - Set zoom level
6. setHighlight(type, indices) - Highlight parts of the model
7. setPBRParams(metallic, roughness) - Set PBR material parameters
8. clearHighlight() - Clear all highlights
9. executeAnalysis(command) - Execute geometry analysis`;
    }

    systemPrompt += `

When a user asks for something, determine if it corresponds to one of these commands. 
If it does, return the command in JSON format with the appropriate parameters.
If it doesn't, provide a helpful response.

Example:
User: "Load the model file cube.stl"
Response: {"command": "loadModel", "params": {"filename": "cube.stl"}}

User: "Move the camera to (1, 2, 3)"
Response: {"command": "setCameraPosition", "params": {"x": 1, "y": 2, "z": 3}}

User: "Hello"
Response: {"response": "Hello! How can I help you with your 3D model?"}
`;

    return systemPrompt;
  }

  async processCommand(command) {
    const systemPrompt = this.getSystemPrompt();

    let response;
    if (this.openai) {
      const completion = await this.openai.chat.completions.create({
        model: 'gpt-3.5-turbo',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: command }
        ]
      });
      response = completion.choices[0].message.content;
    } else if (this.deepseek) {
      const completion = await this.deepseek.chat.completions.create({
        model: 'deepseek-chat',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: command }
        ]
      });
      response = completion.choices[0].message.content;
    } else {
      throw new Error('LLM client not initialized');
    }

    try {
      return JSON.parse(response);
    } catch (e) {
      return { response };
    }
  }
}

module.exports = LLMClient;