import React from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Minus, DollarSign, Percent, BarChart3 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface AnalysisFormatterProps {
  content: string;
}

export function AnalysisFormatter({ content }: AnalysisFormatterProps) {
  // Parse the content - handle both JSON strings and plain markdown
  let analysisText = content;
  
  try {
    // Try to parse as JSON first (in case it's wrapped)
    const parsed = JSON.parse(content);
    if (parsed.analysis) {
      analysisText = parsed.analysis;
    } else if (typeof parsed === 'string') {
      analysisText = parsed;
    }
  } catch {
    // Not JSON, use as-is
    analysisText = content;
  }

  // Split into sections
  const sections = parseAnalysis(analysisText);

  return (
    <div className="space-y-6">
      {/* Executive Summary */}
      {sections.executiveSummary && (
        <Card className="p-5 bg-gradient-to-br from-emerald-50 to-white border-emerald-200">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center">
              <BarChart3 className="h-4 w-4 text-white" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Executive Summary</h3>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                {formatText(sections.executiveSummary)}
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Key Findings */}
      {sections.keyFindings && sections.keyFindings.length > 0 && (
        <Card className="p-5 border-gray-200">
          <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <div className="w-1 h-4 bg-emerald-500 rounded-full" />
            Key Findings
          </h3>
          <ul className="space-y-3">
            {sections.keyFindings.map((finding, i) => (
              <li key={i} className="flex items-start gap-3">
                <div className="flex-shrink-0 w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center mt-0.5">
                  <div className="w-2 h-2 rounded-full bg-emerald-500" />
                </div>
                <p className="text-sm text-gray-700 leading-relaxed flex-1">
                  {formatText(finding)}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Trend Analysis */}
      {sections.trendAnalysis && (
        <Card className="p-5 border-gray-200">
          <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-emerald-600" />
            Trend Analysis
          </h3>
          <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
            {formatText(sections.trendAnalysis)}
          </div>
        </Card>
      )}

      {/* Recommendations */}
      {sections.recommendations && sections.recommendations.length > 0 && (
        <Card className="p-5 border-blue-200 bg-blue-50/50">
          <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <div className="w-1 h-4 bg-blue-500 rounded-full" />
            Recommendations
          </h3>
          <ul className="space-y-3">
            {sections.recommendations.map((rec, i) => (
              <li key={i} className="flex items-start gap-3">
                <div className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-100 flex items-center justify-center mt-0.5">
                  <span className="text-xs font-semibold text-blue-600">{i + 1}</span>
                </div>
                <p className="text-sm text-gray-700 leading-relaxed flex-1">
                  {formatText(rec)}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Other sections */}
      {sections.other && sections.other.length > 0 && (
        <div className="space-y-4">
          {sections.other.map((section, i) => (
            <Card key={i} className="p-5 border-gray-200">
              <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                {formatText(section.content)}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Fallback: if no sections detected, format as plain text */}
      {!sections.executiveSummary && 
       !sections.keyFindings?.length && 
       !sections.trendAnalysis && 
       !sections.recommendations?.length && (
        <Card className="p-5 border-gray-200">
          <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
            {formatText(analysisText)}
          </div>
        </Card>
      )}
    </div>
  );
}

function parseAnalysis(text: string) {
  const sections: {
    executiveSummary?: string;
    keyFindings?: string[];
    trendAnalysis?: string;
    recommendations?: string[];
    other?: Array<{ title: string; content: string }>;
  } = {};

  // Normalize line breaks
  const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
  
  let currentSection: string | null = null;
  let currentContent: string[] = [];
  let keyFindings: string[] = [];
  let recommendations: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    // Detect section headers
    if (line.match(/^##?\s*(Executive Summary|Summary)/i)) {
      if (currentSection && currentContent.length > 0) {
        sections[currentSection as keyof typeof sections] = currentContent.join('\n');
      }
      currentSection = 'executiveSummary';
      currentContent = [];
      continue;
    }
    
    if (line.match(/^##?\s*Key Findings/i)) {
      if (currentSection && currentSection !== 'keyFindings' && currentContent.length > 0) {
        sections[currentSection as keyof typeof sections] = currentContent.join('\n');
      }
      currentSection = 'keyFindings';
      currentContent = [];
      continue;
    }
    
    if (line.match(/^##?\s*Trend Analysis/i)) {
      if (currentSection && currentContent.length > 0) {
        sections[currentSection as keyof typeof sections] = currentContent.join('\n');
      }
      currentSection = 'trendAnalysis';
      currentContent = [];
      continue;
    }
    
    if (line.match(/^##?\s*Recommendations/i)) {
      if (currentSection && currentSection !== 'recommendations' && currentContent.length > 0) {
        sections[currentSection as keyof typeof sections] = currentContent.join('\n');
      }
      currentSection = 'recommendations';
      currentContent = [];
      continue;
    }

    // Handle bullet points
    if (line.match(/^[-*•]\s+/) || line.match(/^\d+\.\s+/)) {
      const bulletText = line.replace(/^[-*•]\s+/, '').replace(/^\d+\.\s+/, '');
      if (currentSection === 'keyFindings') {
        keyFindings.push(bulletText);
      } else if (currentSection === 'recommendations') {
        recommendations.push(bulletText);
      } else {
        currentContent.push(line);
      }
    } else {
      currentContent.push(line);
    }
  }

  // Save final section
  if (currentSection && currentContent.length > 0) {
    if (currentSection === 'keyFindings' && keyFindings.length > 0) {
      sections.keyFindings = keyFindings;
    } else if (currentSection === 'recommendations' && recommendations.length > 0) {
      sections.recommendations = recommendations;
    } else {
      sections[currentSection as keyof typeof sections] = currentContent.join('\n');
    }
  }

  // If we have key findings or recommendations but no section header, extract them
  if (keyFindings.length > 0 && !sections.keyFindings) {
    sections.keyFindings = keyFindings;
  }
  if (recommendations.length > 0 && !sections.recommendations) {
    sections.recommendations = recommendations;
  }

  // Extract executive summary from first paragraph if not found
  if (!sections.executiveSummary && lines.length > 0) {
    const firstParagraph = lines.slice(0, 3).join(' ');
    if (firstParagraph.length > 50 && !firstParagraph.match(/^##/)) {
      sections.executiveSummary = firstParagraph;
    }
  }

  return sections;
}

function formatText(text: string): React.ReactNode {
  if (!text) return null;

  // Format currency: $X.XXM, $X,XXX, etc.
  const currencyRegex = /\$([\d,]+\.?\d*)\s*(M|K|B)?/gi;
  
  // Format percentages: X%, X.X%
  const percentRegex = /(\d+\.?\d*)\%/g;
  
  // Format bold text: *text* or **text**
  const boldRegex = /\*{1,2}([^*]+)\*{1,2}/g;
  
  // Split by newlines to preserve structure
  const parts = text.split('\n').map((line, lineIdx) => {
    if (!line.trim()) return <br key={lineIdx} />;
    
    const elements: React.ReactNode[] = [];
    let lastIndex = 0;
    let key = 0;
    
    // Find all matches
    const matches: Array<{ start: number; end: number; type: 'currency' | 'percent' | 'bold'; content: string }> = [];
    
    // Bold matches
    let match;
    const boldRegex2 = /\*{1,2}([^*]+)\*{1,2}/g;
    while ((match = boldRegex2.exec(line)) !== null) {
      matches.push({
        start: match.index,
        end: match.index + match[0].length,
        type: 'bold',
        content: match[1],
      });
    }
    
    // Currency matches
    const currencyRegex2 = /\$([\d,]+\.?\d*)\s*(M|K|B)?/gi;
    while ((match = currencyRegex2.exec(line)) !== null) {
      matches.push({
        start: match.index,
        end: match.index + match[0].length,
        type: 'currency',
        content: match[0],
      });
    }
    
    // Percent matches
    const percentRegex2 = /(\d+\.?\d*)\%/g;
    while ((match = percentRegex2.exec(line)) !== null) {
      matches.push({
        start: match.index,
        end: match.index + match[0].length,
        type: 'percent',
        content: match[0],
      });
    }
    
    // Sort matches by position
    matches.sort((a, b) => a.start - b.start);
    
    // Build elements
    matches.forEach((m) => {
      // Add text before match
      if (m.start > lastIndex) {
        elements.push(<span key={key++}>{line.substring(lastIndex, m.start)}</span>);
      }
      
      // Add formatted match
      if (m.type === 'bold') {
        elements.push(
          <strong key={key++} className="font-semibold text-gray-900">
            {m.content}
          </strong>
        );
      } else if (m.type === 'currency') {
        elements.push(
          <span key={key++} className="font-semibold text-emerald-600">
            {m.content}
          </span>
        );
      } else if (m.type === 'percent') {
        elements.push(
          <span key={key++} className="font-semibold text-blue-600">
            {m.content}
          </span>
        );
      }
      
      lastIndex = m.end;
    });
    
    // Add remaining text
    if (lastIndex < line.length) {
      elements.push(<span key={key++}>{line.substring(lastIndex)}</span>);
    }
    
    return (
      <p key={lineIdx} className="mb-2 last:mb-0">
        {elements.length > 0 ? elements : line}
      </p>
    );
  });
  
  return <>{parts}</>;
}

