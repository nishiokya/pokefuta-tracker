import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { Database } from '@/types/database';
import sampleManholes from '@/data/sample-manholes.json';

// Transform sample data to match database schema
function transformManholeData(sampleData: any) {
  return {
    id: parseInt(sampleData.id.replace('sample-', '')), // Convert "sample-1" to 1
    title: sampleData.name,
    prefecture: sampleData.prefecture,
    municipality: sampleData.city,
    location: `POINT(${sampleData.longitude} ${sampleData.latitude})`, // PostGIS format
    pokemons: [sampleData.name.replace('マンホール', '')], // Extract Pokemon name
    detail_url: sampleData.source_url
  };
}

export async function POST(request: NextRequest) {
  try {
    // Check if Supabase is configured
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    if (!supabaseUrl || !supabaseKey || supabaseUrl.includes('dummy')) {
      return NextResponse.json({
        success: false,
        error: 'Supabase not configured properly'
      }, { status: 400 });
    }

    // Use service role key to bypass RLS for seeding
    const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!serviceKey) {
      return NextResponse.json({
        success: false,
        error: 'Service role key not configured'
      }, { status: 400 });
    }

    const supabase = createClient<Database>(supabaseUrl, serviceKey);

    // Check if data already exists
    const { data: existingData, error: checkError } = await supabase
      .from('manhole')
      .select('id')
      .limit(1);

    if (checkError) {
      return NextResponse.json({
        success: false,
        error: 'Failed to check existing data',
        details: checkError.message
      }, { status: 500 });
    }

    if (existingData && existingData.length > 0) {
      return NextResponse.json({
        success: false,
        error: 'Data already exists in manhole table',
        count: existingData.length
      }, { status: 400 });
    }

    // Transform sample data to match database schema
    const transformedData = sampleManholes.map(transformManholeData);

    // Insert data
    const { data: insertedData, error: insertError } = await supabase
      .from('manhole')
      .insert(transformedData)
      .select();

    if (insertError) {
      return NextResponse.json({
        success: false,
        error: 'Failed to insert data',
        details: insertError.message
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      message: 'Successfully inserted manhole data',
      count: insertedData?.length || 0,
      data: insertedData
    });

  } catch (error) {
    console.error('Seed error:', error);
    return NextResponse.json({
      success: false,
      error: 'Unexpected error during seeding',
      details: error.message
    }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    // Get current manhole count
    const { data, error } = await supabase
      .from('manhole')
      .select('*');

    if (error) {
      return NextResponse.json({
        success: false,
        error: 'Failed to fetch manhole data',
        details: error.message
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      count: data?.length || 0,
      data: data,
      sampleDataCount: sampleManholes.length,
      transformedSample: sampleManholes.map(transformManholeData)
    });

  } catch (error) {
    return NextResponse.json({
      success: false,
      error: 'Unexpected error',
      details: error.message
    }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    // Delete all manhole data
    const { error } = await supabase
      .from('manhole')
      .delete()
      .neq('id', 0); // Delete all rows

    if (error) {
      return NextResponse.json({
        success: false,
        error: 'Failed to delete data',
        details: error.message
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      message: 'Successfully deleted all manhole data'
    });

  } catch (error) {
    return NextResponse.json({
      success: false,
      error: 'Unexpected error during deletion',
      details: error.message
    }, { status: 500 });
  }
}