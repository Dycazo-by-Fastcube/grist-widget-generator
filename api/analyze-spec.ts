// api/analyze-spec.ts
// Vercel Serverless Function - Analyse la spec et identifie les tables nécessaires

import type { VercelRequest, VercelResponse } from '@vercel/node';

interface RequestBody {
  description: string;
  roles: string[];
  userStories: { [role: string]: string };
}

type Permission = 'create' | 'read' | 'update' | 'delete';
type SuggestedPermissions = { [table: string]: { [role: string]: Permission[] } };

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

Analyse ce besoin, identifie les tables nécessaires et suggère des droits d'accès par rôle.

**Description globale :**
${description}

**Rôles :**
${roles.join(', ')}

**User Stories par rôle :**
${userStoriesText}

**Tâches :**
1. Identifie les 3 à 6 tables principales nécessaires. Nomme-les au singulier, en français (ex: "Collaborateur", "Entretien", "Objectif").
2. Pour chaque table et chaque rôle, suggère les permissions appropriées parmi : "create", "read", "update", "delete". Base-toi sur les user stories et le bon sens métier.

**Réponds UNIQUEMENT avec un JSON valide dans ce format exact :**
{
  "tables": ["Nom1", "Nom2", "Nom3"],
  "suggestedPermissions": {
    "Nom1": {
      "RoleA": ["create", "read", "update", "delete"],
      "RoleB": ["read"]
    },
    "Nom2": {
      "RoleA": ["create", "read", "update", "delete"],
      "RoleB": ["read", "update"]
    }
  }
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
    let suggestedPermissions: SuggestedPermissions = {};
    try {
      const cleanJson = responseText.replace(/```json\n?|\n?```/g, '').trim();
      const parsed = JSON.parse(cleanJson);
      tables = parsed.tables || [];
      suggestedPermissions = parsed.suggestedPermissions || {};
    } catch (parseError) {
      console.error('Failed to parse Claude response:', responseText);
      tables = ['Entité principale', 'Relation', 'Paramètre'];
    }

    if (!Array.isArray(tables) || tables.length === 0) {
      tables = ['Entité principale', 'Relation', 'Paramètre'];
    }

    return res.status(200).json({
      success: true,
      tables,
      suggestedPermissions,
    });

  } catch (error) {
    console.error('Error:', error);
    return res.status(500).json({
      error: 'Internal server error',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
