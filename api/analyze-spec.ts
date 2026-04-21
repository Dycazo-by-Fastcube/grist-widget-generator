// api/analyze-spec.ts
// Vercel Serverless Function - Analyse la spec et identifie les tables nécessaires

import type { VercelRequest, VercelResponse } from '@vercel/node';

interface RequestBody {
  description: string;
  roles: string[];
  userStories: { [role: string]: string };
}

export default async function handler(
  req: VercelRequest,
  res: VercelResponse
) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { description, roles, userStories } = req.body as RequestBody;

    if (!description || !roles || !userStories) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    // Get Claude API key
    const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;

    if (!ANTHROPIC_API_KEY) {
      console.error('Missing ANTHROPIC_API_KEY');
      return res.status(500).json({ error: 'Server configuration error' });
    }

    // Build prompt for Claude
    const userStoriesText = Object.entries(userStories)
      .map(([role, stories]) => `**${role}:**\n${stories}`)
      .join('\n\n');

    const prompt = `Tu es un expert en conception d'applications métier et bases de données.

Analyse ce besoin et identifie les tables principales nécessaires :

**Description globale :**
${description}

**Rôles :**
${roles.join(', ')}

**User Stories par rôle :**
${userStoriesText}

**Tâche :**
Identifie les 3 à 6 tables principales nécessaires pour cette application.
Nomme-les au singulier, en français, de manière claire (ex: "Collaborateur", "Entretien", "Objectif").

**Réponds UNIQUEMENT avec un JSON valide dans ce format exact :**
{
  "tables": ["Nom1", "Nom2", "Nom3"]
}

Pas de texte avant ou après, juste le JSON.`;

    // Call Claude API
    const claudeResponse = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1000,
        messages: [
          {
            role: 'user',
            content: prompt,
          },
        ],
      }),
    });

    if (!claudeResponse.ok) {
      const errorData = await claudeResponse.json();
      console.error('Claude API error:', errorData);
      return res.status(claudeResponse.status).json({
        error: 'Failed to analyze spec',
        details: errorData,
      });
    }

    const claudeData = await claudeResponse.json();
    
    // Extract text from Claude response
    const responseText = claudeData.content?.[0]?.text || '';
    
    // Parse JSON from response
    let tables: string[];
    try {
      // Remove any markdown code blocks if present
      const cleanJson = responseText.replace(/```json\n?|\n?```/g, '').trim();
      const parsed = JSON.parse(cleanJson);
      tables = parsed.tables || [];
    } catch (parseError) {
      console.error('Failed to parse Claude response:', responseText);
      // Fallback: extract table names manually
      tables = ['Entité principale', 'Relation', 'Paramètre'];
    }

    // Validate tables
    if (!Array.isArray(tables) || tables.length === 0) {
      tables = ['Entité principale', 'Relation', 'Paramètre'];
    }

    return res.status(200).json({
      success: true,
      tables: tables,
    });

  } catch (error) {
    console.error('Error:', error);
    return res.status(500).json({
      error: 'Internal server error',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
