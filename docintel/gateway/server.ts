import express from 'express';
import cors from 'cors';
import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import path from 'path';

// Load the proto file
const PROTO_PATH = path.join(__dirname, 'docintel.proto');
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
    keepCase: true,
    longs: String,
    enums: String,
    defaults: true,
    oneofs: true,
});

const proto = grpc.loadPackageDefinition(packageDefinition).docintel as any;

// Create gRPC client pointing to your Python server
const GRPC_HOST = process.env.GRPC_HOST || 'localhost:50051';

const client = new proto.DocumentIntelligence(
    GRPC_HOST,
    grpc.credentials.createInsecure()
);

const app = express();
app.use(cors());
app.use(express.json({limit: '50mb'}));

app.post('/v1/chat/completions', (req, res) => {
    const { question, max_chunks } = req.body;

    if (!question) {
        return res.status(400).json({ error: 'question is required' });
    }

    const request = {
        question,
        max_chunks: max_chunks || 5,
        document_ids: [],
    };

    const stream = client.Query(request);
    const chunks: any[] = [];

    stream.on('data', (response: any) => {
        chunks.push({
            answer: response.token,
            sources: response.sources.map((s: any) => ({
                document_name: s.document_name,
                chunk_text: s.chunk_text,
                similarity_score: s.similarity_score,
            })),
            done: response.done,
        });
    });

    stream.on('end', () => {
        res.json(chunks[0] || { error: 'No response' });
    });

    stream.on('error', (err: any) => {
        console.error('gRPC error:', err);
        res.status(500).json({ error: err.message });
    });
});

app.post('/v1/documents', (req, res) => {
    // For now, accept base64-encoded PDF in JSON
    // A real app would use multipart file upload
    const { filename, content, doc_type } = req.body;

    if (!filename || !content) {
        return res.status(400).json({ error: 'filename and content are required' });
    }

    const request = {
        filename,
        content: Buffer.from(content, 'base64'),
        doc_type: doc_type || '',
    };

    client.IngestDocument(request, (err: any, response: any) => {
        if (err) {
            console.error('gRPC error:', err);
            return res.status(500).json({ error: err.message });
        }
        res.json({
            document_id: response.document_id,
            chunks_created: response.chunks_created,
            status: response.status,
        });
    });
});

app.get('/v1/documents', (req, res) => {
    const request = {
        doc_type: (req.query.doc_type as string) || '',
    };

    client.ListDocuments(request, (err: any, response: any) => {
        if (err) {
            console.error('gRPC error:', err);
            return res.status(500).json({ error: err.message });
        }
        res.json(response.documents);
    });
});





app.listen(3000, () => {
    console.log('Gateway running on http://localhost:3000');
});