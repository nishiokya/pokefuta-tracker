import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { Database } from '@/types/database';
import fs from 'fs';
import path from 'path';

interface NDJSONManhole {
  id: string;
  title: string;
  prefecture: string;
  city: string;
  lat: number;
  lng: number;
  pokemons: string[];
  detail_url: string;
  prefecture_site_url: string;
  source_last_checked: string;
}

export async function POST(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    // Read NDJSON file
    const ndjsonPath = path.join(process.cwd(), '..', 'web', 'pokefuta.ndjson');

    if (!fs.existsSync(ndjsonPath)) {
      return NextResponse.json({
        success: false,
        error: 'NDJSON file not found',
        path: ndjsonPath
      }, { status: 404 });
    }

    const fileContent = fs.readFileSync(ndjsonPath, 'utf8');
    const lines = fileContent.trim().split('\n');

    // Parse NDJSON and get latest entry for each unique ID
    const manholeMap = new Map<string, NDJSONManhole>();

    for (const line of lines) {
      try {
        const manhole: NDJSONManhole = JSON.parse(line);
        const existingManhole = manholeMap.get(manhole.id);

        // Keep the latest entry (by source_last_checked date)
        if (!existingManhole || new Date(manhole.source_last_checked) > new Date(existingManhole.source_last_checked)) {
          manholeMap.set(manhole.id, manhole);
        }
      } catch (parseError) {
        console.warn('Failed to parse line:', line, parseError);
        continue;
      }
    }

    const uniqueManholes = Array.from(manholeMap.values());
    console.log(`Found ${uniqueManholes.length} unique manholes from ${lines.length} total entries`);

    // Transform to database format
    const transformedManholes = uniqueManholes.map((manhole) => ({
      id: parseInt(manhole.id),
      title: `${manhole.title}+${manhole.id}`,
      prefecture: manhole.prefecture,
      municipality: manhole.city,
      location: `POINT(${manhole.lng} ${manhole.lat})`,
      pokemons: manhole.pokemons,
      detail_url: manhole.detail_url,
      source_last_checked: manhole.source_last_checked,
      created_at: new Date().toISOString()
    }));

    // Insert in batches to avoid timeout
    const batchSize = 50;
    const batches = [];
    for (let i = 0; i < transformedManholes.length; i += batchSize) {
      batches.push(transformedManholes.slice(i, i + batchSize));
    }

    let totalInserted = 0;
    const errors = [];

    for (let i = 0; i < batches.length; i++) {
      const batch = batches[i];
      console.log(`Inserting batch ${i + 1}/${batches.length} (${batch.length} items)`);

      const { data, error } = await supabase
        .from('manhole')
        .insert(batch)
        .select();

      if (error) {
        console.error(`Batch ${i + 1} error:`, error);
        errors.push({
          batch: i + 1,
          error: error.message,
          items: batch.length
        });
      } else {
        totalInserted += data?.length || 0;
      }
    }

    return NextResponse.json({
      success: errors.length === 0,
      message: errors.length === 0
        ? `Successfully inserted ${totalInserted} manholes`
        : `Partially successful: ${totalInserted} inserted, ${errors.length} batches failed`,
      total_processed: uniqueManholes.length,
      total_inserted: totalInserted,
      total_batches: batches.length,
      errors: errors.length > 0 ? errors : undefined,
      sample_manholes: transformedManholes.slice(0, 3)
    });

  } catch (error) {
    console.error('Insert NDJSON error:', error);
    return NextResponse.json({
      success: false,
      error: 'Unexpected error during NDJSON import',
      details: error.message
    }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  try {
    // Show status/preview of NDJSON data
    const ndjsonPath = path.join(process.cwd(), '..', 'web', 'pokefuta.ndjson');

    if (!fs.existsSync(ndjsonPath)) {
      return NextResponse.json({
        success: false,
        error: 'NDJSON file not found',
        path: ndjsonPath
      }, { status: 404 });
    }

    const fileContent = fs.readFileSync(ndjsonPath, 'utf8');
    const lines = fileContent.trim().split('\n');

    // Parse first few entries as sample
    const sampleEntries = [];
    const uniqueIds = new Set();

    for (let i = 0; i < Math.min(lines.length, 10); i++) {
      try {
        const entry = JSON.parse(lines[i]);
        sampleEntries.push(entry);
        uniqueIds.add(entry.id);
      } catch (parseError) {
        continue;
      }
    }

    // Count unique IDs by parsing all lines
    const allUniqueIds = new Set();
    for (const line of lines) {
      try {
        const entry = JSON.parse(line);
        allUniqueIds.add(entry.id);
      } catch (parseError) {
        continue;
      }
    }

    return NextResponse.json({
      success: true,
      file_path: ndjsonPath,
      total_lines: lines.length,
      unique_manholes: allUniqueIds.size,
      sample_entries: sampleEntries,
      ready_to_import: true
    });

  } catch (error) {
    return NextResponse.json({
      success: false,
      error: error.message
    }, { status: 500 });
  }
}