const { OpenAI } = require('openai');
const http = require('http');
const fs = require('fs');
const path = require('path');

// 初始化 OpenAI 客户端
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// 系统提示
const systemPrompt = `
You are a CAD assistant that helps users interact with a 3D model viewer. 
You can execute commands to control the viewer, load models, and analyze geometry.

Available commands:
1. loadModel(filename) - Load a 3D model file
2. resetCamera() - Reset camera to default position
3. setCameraPosition(x, y, z) - Set camera position
4. setCameraRotation(pitch, yaw) - Set camera rotation
5. setZoom(zoom) - Set zoom level
6. setHighlight(type, indices) - Highlight parts of the model
7. setPBRParams(metallic, roughness) - Set PBR material parameters
8. clearHighlight() - Clear all highlights
9. executeAnalysis(command) - Execute geometry analysis

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

// 处理用户输入
async function processUserInput(input) {
  try {
    // 生成响应
    const result = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: input }
      ]
    });

    const response = result.choices[0].message.content;
    
    try {
      // 尝试解析为 JSON
      return JSON.parse(response);
    } catch (e) {
      // 如果不是 JSON，返回普通响应
      return { response };
    }
  } catch (error) {
    console.error('Error processing LLM request:', error);
    return { response: 'Sorry, I encountered an error processing your request.' };
  }
}

// 发送命令到 C++ 后端
function sendCommandToBackend(command) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: 8080,
      path: '/',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          resolve({ response: data });
        }
      });
    });

    req.on('error', (error) => {
      console.error('Error sending command to backend:', error);
      reject(error);
    });

    req.write(JSON.stringify(command));
    req.end();
  });
}

// 创建 HTTP 服务器
const server = http.createServer((req, res) => {
  // 处理静态文件
  let filePath = '.' + req.url;
  if (filePath === './') {
    filePath = './index.html';
  }

  const extname = String(path.extname(filePath)).toLowerCase();
  const mimeTypes = {
    '.html': 'text/html',
    '.js': 'text/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpg',
    '.gif': 'image/gif',
    '.wav': 'audio/wav',
    '.mp4': 'video/mp4',
    '.woff': 'application/font-woff',
    '.ttf': 'application/font-ttf',
    '.eot': 'application/vnd.ms-fontobject',
    '.otf': 'application/font-otf',
    '.svg': 'application/image/svg+xml'
  };

  const contentType = mimeTypes[extname] || 'application/octet-stream';

  fs.readFile(filePath, (error, content) => {
    if (error) {
      if (error.code == 'ENOENT') {
        // 处理 API 请求
        if (req.method === 'POST' && req.url === '/api/process') {
          let body = '';
          req.on('data', (chunk) => {
            body += chunk;
          });
          req.on('end', async () => {
            try {
              const data = JSON.parse(body);
              if (data.message) {
                console.log('Received message:', data.message);
                
                // 处理用户输入
                const result = await processUserInput(data.message);
                console.log('Processed result:', result);
                
                // 如果是命令，发送到后端
                if (result.command) {
                  try {
                    const backendResponse = await sendCommandToBackend(result);
                    console.log('Backend response:', backendResponse);
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify(backendResponse));
                  } catch (error) {
                    console.error('Error sending to backend:', error);
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify(result));
                  }
                } else {
                  res.writeHead(200, { 'Content-Type': 'application/json' });
                  res.end(JSON.stringify(result));
                }
              } else {
                res.writeHead(400);
                res.end('Bad request');
              }
            } catch (error) {
              console.error('Error processing request:', error);
              res.writeHead(500);
              res.end('Internal server error');
            }
          });
        } else {
          res.writeHead(404);
          res.end('File not found');
        }
      } else {
        res.writeHead(500);
        res.end('Sorry, check with the site admin for error: ' + error.code + ' ..\n');
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content, 'utf-8');
    }
  });
});

// 启动服务器
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});

// 测试函数
async function test() {
  const testInputs = [
    'Load the model file cube.stl',
    'Move the camera to (1, 2, 3)',
    'Reset the camera',
    'Set zoom to 2.0',
    'Hello'
  ];

  for (const input of testInputs) {
    console.log('Input:', input);
    const result = await processUserInput(input);
    console.log('Output:', result);
    console.log('---');
  }
}

if (require.main === module) {
  // 测试函数
  // test();
}